#!/usr/bin/env python3
"""Resume the fixed GTEx Evo2-20B embedding job on a native NVIDIA FP8 GPU.

Paths are relative to this packet, not the caller's current directory. No labels
are read. Channel-chunked dense operations preserve the full 131,072-bp window.
The bundled checkpoint records Transformer Engine scaling and RNG state; do not
delete it, change sequence order, or split its unfinished rows between workers.
"""
from pathlib import Path
import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import signal
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WEIGHT_SHA256 = "979b345dc700a9cae6b63f570d9b3f438e31a68dd8dc0bc0d8d2a0fcd3caf791"
REVISION = "8b0f0a9a70c66367ed181a17d049b95699a28fed"
PREPARED_PROTOCOL_SHA256 = "b1d523ae578528275aff50cc2785994f55c1ebcb1d4abdca105d716d4047f32b"
SEQUENCES_SHA256 = "264314da83efc936dbbcfce492fdb4e45ecdbd05e6dc014ce26cce6172a9579f"
THRESHOLD = 0.005
N_GENES = 19282
SEQ_LEN = 131072
SEED = 20260822


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n")
    temp.replace(path)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint", type=Path,
                   help="Pinned evo2_20b.pt; downloaded separately, always SHA256-checked")
    p.add_argument("--prepared", type=Path, default=ROOT / "data/prepared")
    p.add_argument("--resume-source", type=Path, default=ROOT / "data/resume")
    p.add_argument("--output", type=Path, default=ROOT / "run/extraction")
    p.add_argument("--validate-only", action="store_true",
                   help="Run three short, three full-window and resume/replay controls, then stop")
    p.add_argument("--inspect-inputs", action="store_true",
                   help="CPU-only shape/hash check of supplied inputs, then exit (no weights needed)")
    p.add_argument("--max-new-genes", type=int,
                   help="Optional bounded smoke run; cleanly checkpoint after this many new genes")
    p.add_argument("--allow-version-drift", action="store_true",
                   help="Record an explicit environment difference; numerical gates still mandatory")
    p.add_argument("--threads", type=int, default=8)
    p.add_argument("--allow-multi-gpu-shard", action="store_true",
                   help="Explicit experimental block sharding; all frozen numerical gates still apply")
    return p


def main():
    a = parser().parse_args()
    if a.max_new_genes is not None and a.max_new_genes < 1:
        raise SystemExit("--max-new-genes must be positive")
    if a.threads < 1:
        raise SystemExit("--threads must be positive")
    import numpy as np
    if digest(a.prepared / "protocol.json") != PREPARED_PROTOCOL_SHA256:
        raise SystemExit("Prepared protocol hash differs from the frozen benchmark.")
    if digest(a.prepared / "sequences.npy") != SEQUENCES_SHA256:
        raise SystemExit("Prepared sequence hash differs from the frozen benchmark.")
    if a.inspect_inputs:
        sequence = np.load(a.prepared / "sequences.npy", mmap_mode="r")
        emb = np.load(a.resume_source / "embeddings.npy", mmap_mode="r")
        done = np.load(a.resume_source / "completed.npy", mmap_mode="r")
        if sequence.shape != (N_GENES, SEQ_LEN) or sequence.dtype != np.uint8:
            raise SystemExit("Invalid sequence shape or dtype.")
        if emb.shape != (N_GENES, 512) or emb.dtype != np.float16:
            raise SystemExit("Invalid embedding shape or dtype.")
        if done.shape != (N_GENES,) or done.dtype != np.bool_:
            raise SystemExit("Invalid completion mask.")
        if not done[0] or not np.isfinite(emb[done]).all():
            raise SystemExit("Invalid resume controls or nonfinite completed features.")
        print(json.dumps(dict(cpu_input_checks_passed=True, n_genes=N_GENES,
              completed=int(done.sum()), remaining=int((~done).sum()),
              sequence_sha256=SEQUENCES_SHA256), indent=2))
        return
    if a.checkpoint is None:
        raise SystemExit("--checkpoint is required for GPU validation/extraction.")
    # HPC login environments may point default caches at an unwritable /.cache.
    cache = ROOT / "run/cache"
    os.environ.setdefault("XDG_CACHE_HOME", str(cache))
    os.environ.setdefault("TORCHINDUCTOR_CACHE_DIR", str(cache / "inductor"))
    os.environ.setdefault("TRITON_CACHE_DIR", str(cache / "triton"))
    # These exact Evo2/Vortex Python sources came from the accepted installation.
    vendor = ROOT / "env/vendor"
    sys.path.insert(0, str(vendor))
    import torch
    from evo2 import Evo2
    from transformer_engine.pytorch.module.base import TransformerEngineBaseModule
    from projection_frozen import SRHTProjection
    from gtex_evo2_memory_frozen import install

    if not torch.cuda.is_available() or torch.version.hip:
        raise SystemExit("This protocol requires native NVIDIA FP8; ROCm/BF16 substitutes failed controls.")
    n_devices = torch.cuda.device_count()
    if n_devices != 1 and not (a.allow_multi_gpu_shard and n_devices == 2):
        raise SystemExit("Expose exactly one GPU, for example CUDA_VISIBLE_DEVICES=0. No implicit sharding.")
    gpu = torch.cuda.get_device_properties(0)
    if gpu.major < 9:
        raise SystemExit("A Hopper-or-newer NVIDIA GPU with native FP8 is required.")
    if any(torch.cuda.get_device_properties(d).major < 9 for d in range(n_devices)):
        raise SystemExit("All GPUs must support native Hopper FP8.")
    if n_devices == 1 and gpu.total_memory < 90_000_000_000:
        raise SystemExit("This unchanged full-context runner needs ~94 GB GPU memory; use H200/GH200, not H100 80GB.")
    expected = {"torch": "2.13.0", "transformer_engine": "2.18.0",
                "transformer_engine_torch": "2.18.0", "flash_attn": "2.8.0.post2",
                "numpy": "2.5.2", "einops": "0.8.2"}
    versions = {k: importlib.metadata.version(k) for k in expected}
    differences = {k: {"expected": v, "actual": versions[k]}
                   for k, v in expected.items() if versions[k].split("+")[0] != v}
    if torch.version.cuda != "13.0":
        differences["torch_cuda"] = {"expected": "13.0", "actual": torch.version.cuda}
    if differences and not a.allow_version_drift:
        raise SystemExit("Environment differs from the source: " + json.dumps(differences)
                         + ". See env/README.md; do not silently bypass this check.")
    for filename in ("sequences.npy", "protocol.json"):
        if not (a.prepared / filename).is_file():
            raise SystemExit(f"Missing prepared input: {a.prepared / filename}")
    if digest(a.prepared / "protocol.json") != PREPARED_PROTOCOL_SHA256:
        raise SystemExit("Prepared protocol hash differs from the frozen benchmark.")
    if not a.checkpoint.is_file():
        raise SystemExit("Missing checkpoint; run scripts/extraction/download_checkpoint.py first.")
    print("Verifying pinned checkpoint SHA256 (47.9 GB file)", flush=True)
    if digest(a.checkpoint) != WEIGHT_SHA256:
        raise SystemExit("Checkpoint hash mismatch; do not use these weights.")
    manifest = json.loads((vendor / "SOURCE_HASHES.json").read_text())
    for rel, expected_hash in manifest["sha256"].items():
        if digest(vendor / rel) != expected_hash:
            raise SystemExit(f"Vendored runtime modified: {rel}")
    output = a.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    lock = (output / ".writer.lock").open("a+")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Another extractor already owns this output directory.")
    if (output / "COMPLETE.json").exists():
        print("Already complete:", output, flush=True)
        return
    sequence = np.load(a.prepared / "sequences.npy", mmap_mode="r")
    if sequence.shape != (N_GENES, SEQ_LEN) or sequence.dtype != np.uint8:
        raise SystemExit(f"Unexpected prepared sequence array: {sequence.shape}, {sequence.dtype}")
    if not (output / "resume_state.pt").exists():
        # Copy initialization atomically. The snapshot's done mask is authoritative.
        if any((output / x).exists() for x in ("embeddings.npy", "completed.npy")):
            raise SystemExit("Incomplete initialization: review output instead of overwriting it.")
        for name in ("embeddings.npy", "completed.npy", "resume_state.pt"):
            if not (a.resume_source / name).is_file():
                raise SystemExit(f"Missing resume snapshot: {a.resume_source / name}")
        for name in ("embeddings.npy", "completed.npy", "resume_state.pt"):
            tmp = output / (name + ".init")
            shutil.copy2(a.resume_source / name, tmp)
            tmp.replace(output / name)
    emb = np.lib.format.open_memmap(output / "embeddings.npy", mode="r+")
    done = np.lib.format.open_memmap(output / "completed.npy", mode="r+")
    if emb.shape != (N_GENES, 512) or emb.dtype != np.float16:
        raise SystemExit("Embedding array must be float16, shape (19282,512).")
    if done.shape != (N_GENES,) or done.dtype != np.bool_:
        raise SystemExit("Completion mask must be bool, shape (19282,).")
    # Trusted project-generated checkpoint, not an arbitrary downloaded pickle.
    resume = torch.load(output / "resume_state.pt", map_location="cpu", weights_only=False)
    if np.asarray(resume["done"]).shape != (N_GENES,):
        raise SystemExit("Bad mask in resume checkpoint.")
    done[:] = resume["done"]
    done.flush()
    if not np.isfinite(emb[done]).all() or not done[0]:
        raise SystemExit("Resume snapshot has invalid completed features or lacks control gene 0.")
    protocol = dict(model="arcinstitute/evo2_20b", revision=REVISION,
                    checkpoint_sha256=WEIGHT_SHA256, representation_unchanged=True,
                    native_fp8=True, implementation="dense", window_length=SEQ_LEN,
                    selected_layer="blocks.20.mlp.l3", projection_seed=SEED,
                    pooling="4096-token chunked float32 sums; float16 before SRHT512",
                    control_threshold_relative_l2=THRESHOLD,
                    source_resume_sha256=digest(a.resume_source / "resume_state.pt"),
                    source_embedding_sha256=digest(a.resume_source / "embeddings.npy"),
                    source_mask_sha256=digest(a.resume_source / "completed.npy"),
                    source_prepared_protocol_sha256=PREPARED_PROTOCOL_SHA256,
                    source_sequences_sha256=SEQUENCES_SHA256,
                    script_sha256=digest(Path(__file__)),
                    implementation_sha256=digest(HERE / "gtex_evo2_memory_frozen.py"),
                    projection_sha256=digest(HERE / "projection_frozen.py"),
                    vendor_hash_manifest_sha256=digest(vendor / "SOURCE_HASHES.json"))
    protocol.update(multi_gpu_shard=bool(a.allow_multi_gpu_shard), gpu_count=n_devices,
                    state_adapter_sha256=digest(HERE / "multi_gpu_state.py"))
    if (output / "protocol.json").exists():
        if json.loads((output / "protocol.json").read_text()) != protocol:
            raise SystemExit("Protocol or source snapshot changed; use a new output directory.")
    else:
        write_json(output / "protocol.json", protocol)
    environment = dict(python=sys.version, platform=platform.platform(), versions=versions,
                       torch_cuda=torch.version.cuda, differences=differences,
                       gpu=gpu.name, gpu_total_memory=gpu.total_memory,
                       compute_capability=[gpu.major, gpu.minor], native_fp8=True,
                       process_id=os.getpid(), started_unix=time.time())
    environment.update(multi_gpu_shard=bool(a.allow_multi_gpu_shard), gpu_count=n_devices,
                       gpus=[dict(index=d, name=torch.cuda.get_device_properties(d).name,
                                  memory=torch.cuda.get_device_properties(d).total_memory)
                             for d in range(n_devices)])
    write_json(output / f"environment-{os.getpid()}.json", environment)
    write_json(output / "ENVIRONMENT.json", environment)
    torch.set_num_threads(a.threads)
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    print("Loading Evo2 20B", flush=True)
    if a.allow_multi_gpu_shard:
        from multi_gpu_state import install as install_state_adapter
        install_state_adapter()
    wrapper = Evo2("evo2_20b", local_path=str(a.checkpoint.resolve()), use_kernels=False)
    model = wrapper.model.eval().requires_grad_(False)
    tokenizer = wrapper.tokenizer
    install(model)
    projection = SRHTProjection.seeded(8192, 512, SEED)
    captured = {}

    class Captured(Exception):
        pass

    def hook(module, inputs, outputs):
        h = outputs.detach()
        sums = torch.zeros((h.shape[0], h.shape[-1]), device=h.device, dtype=torch.float32)
        for start in range(0, h.shape[1], 4096):
            sums.add_(h[:, start:start + 4096].float().sum(1))
        captured["raw"] = (sums / h.shape[1]).cpu().numpy().astype(np.float16)
        raise Captured()

    model.get_submodule("blocks.20.mlp.l3").register_forward_hook(hook)
    lookup = np.array(list(b"ACGTN"), dtype=np.uint8)

    def extract_string(s):
        ids = torch.tensor([tokenizer.tokenize(s)], device="cuda", dtype=torch.long)
        with torch.inference_mode():
            try:
                model(ids)
            except Captured:
                pass
        values = projection.transform(captured.pop("raw")).astype(np.float16)[0]
        if values.shape != (512,) or not np.isfinite(values).all():
            raise RuntimeError("Non-finite or malformed projected feature.")
        return values

    def extract(i):
        codes = sequence[i]
        if codes.max() > 4:
            raise RuntimeError(f"Invalid sequence coding at index {i}.")
        return extract_string(lookup[codes].tobytes().decode("ascii"))

    def error(actual, reference):
        return float(np.linalg.norm(actual.astype(float) - reference.astype(float))
                     / np.linalg.norm(reference.astype(float)))

    # Deliberately reproduce the initial-state control order of the accepted probe.
    controls = np.load(HERE / "controls/reference.npz", allow_pickle=False)
    control_report = dict(short=[], full=[], tolerance_relative_l2=THRESHOLD)
    for i, s in enumerate(controls["short_sequences"].astype(str)):
        e = error(extract_string(s), controls["short_features"][i])
        control_report["short"].append(e)
        if e >= THRESHOLD:
            write_json(output / "FAILED_CONTROLS.json", control_report)
            raise RuntimeError(f"Short numerical control {i} failed: {e}")
    for index in range(21, 24):
        model.blocks[index].to("cpu")
    for d in range(n_devices):
        with torch.cuda.device(d):
            torch.cuda.empty_cache()
    for i, codes in enumerate(controls["long_sequences"][:3]):
        value = extract_string(lookup[codes].tobytes().decode("ascii"))
        e = error(value, controls["long_features"][i])
        control_report["full"].append(e)
        if e >= THRESHOLD:
            write_json(output / "FAILED_CONTROLS.json", control_report)
            raise RuntimeError(f"Full-window numerical control {i} failed: {e}")
    extra = {name: module for name, module in model.named_modules()
             if isinstance(module, TransformerEngineBaseModule)}

    def capture():
        return dict(extra={n: m.get_extra_state() for n, m in extra.items()},
                    cpu_rng=torch.get_rng_state(), cuda_rng=torch.cuda.get_rng_state_all(),
                    done=np.asarray(done).copy())

    @torch.inference_mode()
    def restore(state):
        if set(state["extra"]) != set(extra):
            raise RuntimeError("Transformer Engine module names differ from the accepted snapshot.")
        saved_rng = state["cuda_rng"]
        if len(saved_rng) != n_devices:
            if not (a.allow_multi_gpu_shard and len(saved_rng) == 1):
                raise RuntimeError("Unexpected saved CUDA RNG device count.")
            # Block sharding preserves serial gene order. Evaluation disables
            # dropout; device 0 retains the source RNG and added devices retain
            # their seeded states. Exact replay remains mandatory below.
            saved_rng = list(saved_rng) + [torch.cuda.get_rng_state(d) for d in range(1, n_devices)]
        for name, value in state["extra"].items():
            extra[name].set_extra_state(value)
        torch.set_rng_state(state["cpu_rng"])
        torch.cuda.set_rng_state_all(saved_rng)

    def checkpoint():
        emb.flush()
        done.flush()
        temporary = output / "resume_state.tmp.pt"
        torch.save(capture(), temporary)
        temporary.replace(output / "resume_state.pt")

    # Restore AFTER controls: test calls must not advance the production FP8 state.
    restore(resume)
    before = capture()
    first = extract(0)
    restore(before)
    second = extract(0)
    np.testing.assert_array_equal(first, second)
    resume_error = error(first, emb[0])
    if resume_error >= THRESHOLD:
        raise RuntimeError(f"Existing-cache control fails after resume: {resume_error}")
    restore(before)
    control_report.update(exact_replay=True, resume_control_relative_l2=resume_error,
                          completed_initially=int(done.sum()), passed=True,
                          process_id=os.getpid(), checked_unix=time.time())
    write_json(output / "RESUME_VALIDATION.json", control_report)
    print("Validated controls:", json.dumps(control_report), flush=True)
    if a.validate_only:
        return
    stop = False

    def request_stop(signum, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    start = time.monotonic()
    initial = int(done.sum())
    last = start
    for i in np.flatnonzero(~done):
        emb[i] = extract(i)
        done[i] = True
        count = int(done.sum())
        bounded_stop = a.max_new_genes is not None and count - initial >= a.max_new_genes
        now = time.monotonic()
        if now - last >= 60 or stop or bounded_stop:
            checkpoint()
            elapsed = now - start
            progress = dict(completed=count, total=N_GENES, seconds=elapsed,
                            genes_per_second=(count - initial) / elapsed,
                            estimated_remaining_hours=(N_GENES - count) * elapsed
                            / max(1, count - initial) / 3600,
                            updated_unix=time.time(), pid=os.getpid(), implementation="dense")
            write_json(output / "progress.json", progress)
            print("PROGRESS", json.dumps(progress), flush=True)
            last = now
        if stop or bounded_stop:
            print("Checkpointed clean stop.", flush=True)
            return
    checkpoint()
    if not done.all() or not np.isfinite(emb).all():
        raise RuntimeError("Final array is incomplete or non-finite.")
    write_json(output / "COMPLETE.json", dict(n_genes=N_GENES,
               embedding_sha256=digest(output / "embeddings.npy"), finished_unix=time.time()))
    print("COMPLETE", output, flush=True)


if __name__ == "__main__":
    main()
