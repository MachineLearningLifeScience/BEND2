"""Extract one uniform FP32 CENO representation for the complete OpenSplice task.

No rows from the historical BF16 CUDA cache enter this matrix. The pilot compares
the accelerated Mamba scan with CENO's released torch_forward, before inference.
"""
from pathlib import Path
import argparse, hashlib, json, time, types
import numpy as np
import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

p = argparse.ArgumentParser()
p.add_argument('--root', type=Path, required=True)
p.add_argument('--rank', type=int, default=0)
p.add_argument('--workers', type=int, default=1)
p.add_argument('--batch-size', type=int, default=32)
p.add_argument('--pilot', action='store_true')
a = p.parse_args()
R = a.root
M = Path('/scratch/project_465003339/ajeppese/gimbench-gtex-ceno-20260923/extra-models-direct/models--CladeTeam--CENO-1B-1m/snapshots/fa8089cb4c9e22665190a2a7514a6346ec37d95d')

def sha(path):
    with open(path, 'rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()

def rel(actual, reference):
    return float(np.linalg.norm(actual.astype(float) - reference) / np.linalg.norm(reference))

def delta(values):
    return values[1::2] - values[::2]

def pair_delta_errors(actual, reference):
    return [rel(x, y) for x, y in zip(delta(actual), delta(reference))]

protocol_path = R / 'prepared/FULL_PROTOCOL.json'
protocol = json.loads(protocol_path.read_text())
protocol_hash = sha(protocol_path)
assert sha(R / 'prepared/full.parquet') == protocol['full_sha256']
sequences = pd.read_parquet(R / 'prepared/full.parquet').sequence.to_numpy()
assert len(sequences) == protocol['full_unique'] == 590703
torch.manual_seed(20260822)
torch.set_num_threads(6)
torch.backends.cuda.matmul.allow_tf32 = False
torch.backends.cudnn.allow_tf32 = False
tok = AutoTokenizer.from_pretrained(M, trust_remote_code=True, local_files_only=True)
assert tok.padding_side == 'right'
model, loading = AutoModelForCausalLM.from_pretrained(
    M, trust_remote_code=True, local_files_only=True, torch_dtype=torch.float32,
    use_safetensors=True, output_loading_info=True)
assert not any(loading.get(k) for k in ['missing_keys', 'mismatched_keys', 'error_msgs']), loading
model = model.cuda().eval().requires_grad_(False)
assert model.config.use_mamba_kernels

def extract(seq, extra_padding=0):
    token_args = dict(padding=True, truncation=False, return_tensors='pt')
    if extra_padding:
        unpadded = tok(list(seq), **token_args)
        token_args.update(padding='max_length', max_length=unpadded['input_ids'].shape[1] + extra_padding)
    tokens = {k: v.cuda() for k, v in tok(list(seq), **token_args).items()}
    mask = tokens.get('attention_mask', torch.ones_like(tokens['input_ids'])).bool()
    for special_id in tok.all_special_ids:
        mask &= tokens['input_ids'] != special_id
    assert mask.any(1).all()
    # The tokenizer and released causal forward retain right-padding semantics;
    # the mean excludes special/pad tokens, exactly as the original extractor.
    with torch.inference_mode():
        h = model.backbone(**tokens, use_cache=False, output_hidden_states=False).last_hidden_state
        assert h.dtype == torch.float32
        pooled = (h * mask.unsqueeze(-1)).sum(1) / mask.sum(1, keepdim=True)
    result = pooled.cpu().numpy()
    assert result.shape == (len(seq), 1024) and np.isfinite(result).all()
    return result

meta = dict(protocol_sha256=protocol_hash, script_sha256=sha(Path(__file__)),
            model_revision=protocol['checkpoint_revision'],
            model_weights_sha256=sha(M / 'model.safetensors'),
            model_code_sha256=sha(M / 'modeling_ceno.py'),
            torch=torch.__version__, device=torch.cuda.get_device_name(), loading=loading,
            rank=a.rank, workers=a.workers, batch_size=a.batch_size,
            precision='float32', autocast=False, tf32=False)
control_path = R / 'prepared/full-native-controls.npz'

if a.pilot:
    # Count the actual released implementation calls, so the comparison cannot
    # accidentally compare the fallback implementation against itself.
    calls = dict(cuda_kernels_forward=0, torch_forward=0)
    def counted(name, original):
        def wrapper(self, *args, **kwargs):
            calls[name] += 1
            return original(*args, **kwargs)
        return wrapper
    mixers = [m for m in model.modules() if m.__class__.__name__ == 'CENOMamba2Mixer']
    assert mixers
    for mixer in mixers:
        for method in calls:
            setattr(mixer, method, types.MethodType(counted(method, getattr(mixer, method)), mixer))
    # Adjacent sequences form experimentally observed ref/alt pairs. Include
    # SNVs and deletions so padding is exercised at the level of effect vectors.
    pairs = pd.read_parquet(R / 'prepared/native-pairs.parquet')
    control_sequences = pairs[['sequence_ref', 'sequence_alt']].to_numpy().reshape(-1).astype(str)
    accelerated = extract(control_sequences)
    assert calls['cuda_kernels_forward'] == len(mixers) and calls['torch_forward'] == 0, calls
    singles = np.concatenate([extract([s]) for s in control_sequences])
    permutation = np.random.default_rng(20260822).permutation(len(control_sequences))
    permuted = extract(control_sequences[permutation])[np.argsort(permutation)]
    padded = extract(control_sequences, extra_padding=17)
    # Switching this documented model option selects CENO's own torch_forward.
    # It independently computes scan and convolution with ordinary torch ops.
    model.config.use_mamba_kernels = False
    accelerated_calls = calls['cuda_kernels_forward']
    native = np.concatenate([extract([s]) for s in control_sequences])
    assert calls['cuda_kernels_forward'] == accelerated_calls, calls
    assert calls['torch_forward'] == len(mixers) * len(control_sequences), calls
    model.config.use_mamba_kernels = True
    controls = dict(
        pairs=len(pairs), types=pairs.intervention_type.value_counts().to_dict(),
        native_embedding_relative_l2=rel(accelerated, native),
        native_delta_relative_l2=rel(delta(accelerated), delta(native)),
        singleton_embedding_relative_l2=rel(accelerated, singles),
        singleton_delta_relative_l2=rel(delta(accelerated), delta(singles)),
        permutation_embedding_relative_l2=rel(accelerated, permuted),
        permutation_delta_relative_l2=rel(delta(accelerated), delta(permuted)),
        padding_embedding_relative_l2=rel(accelerated, padded),
        padding_delta_relative_l2=rel(delta(accelerated), delta(padded)),
        embedding_limit=.005, delta_limit=.02)
    meta['controls'] = controls
    meta['implementation_calls'] = dict(calls)
    meta['per_pair_delta_relative_l2'] = {
        name: pair_delta_errors(accelerated, expected)
        for name, expected in [('native', native), ('singleton', singles),
                               ('permutation', permuted), ('padding', padded)]}
    print('NATIVE_CONTROLS', json.dumps(controls), flush=True)
    (R / 'full-pilot-diagnostic.json').write_text(json.dumps(meta, indent=2) + '\n')
    for name, value in controls.items():
        if name.endswith('embedding_relative_l2'):
            assert value < .005, (name, value)
        if name.endswith('delta_relative_l2'):
            assert value < .02, (name, value)
    for name, errors in meta['per_pair_delta_relative_l2'].items():
        assert max(errors) < .02, (name, errors)
    # Production workers compare to the independent native reference.
    np.savez(control_path, sequences=control_sequences, embeddings=native,
             protocol_sha256=protocol_hash)
    with np.load(control_path, allow_pickle=False) as saved:
        assert np.array_equal(saved['sequences'], control_sequences)
        assert np.array_equal(saved['embeddings'], native)
    meta['native_controls_sha256'] = sha(control_path)
    timings = []
    sample_ids = np.random.default_rng(20260822).permutation(len(sequences))[:1024]
    for batch in [32, 64, 128]:
        torch.cuda.reset_peak_memory_stats()
        extract(sequences[sample_ids[:batch]])
        torch.cuda.synchronize()
        start = time.monotonic()
        for k in range(5):
            extract(sequences[sample_ids[batch * (k + 1):batch * (k + 2)]])
        torch.cuda.synchronize()
        timing = dict(batch=batch, sequences_per_second=5 * batch / (time.monotonic() - start),
                      peak_gb=torch.cuda.max_memory_allocated() / 1e9)
        timings.append(timing)
        print('BENCHMARK', json.dumps(timing), flush=True)
    meta['benchmarks'] = timings
    meta['status'] = 'passed'
    (R / 'full-pilot.json').write_text(json.dumps(meta, indent=2) + '\n')
    raise SystemExit()

pilot = json.loads((R / 'full-pilot.json').read_text())
assert pilot['status'] == 'passed' and pilot['protocol_sha256'] == protocol_hash
assert pilot['script_sha256'] == meta['script_sha256']
assert pilot['native_controls_sha256'] == sha(control_path)
ref = np.load(control_path)
assert str(ref['protocol_sha256']) == protocol_hash
actual = extract(ref['sequences'])
control = dict(embedding_relative_l2=rel(actual, ref['embeddings']),
               delta_relative_l2=rel(delta(actual), delta(ref['embeddings'])),
               per_pair_delta_relative_l2=pair_delta_errors(actual, ref['embeddings']))
assert control['embedding_relative_l2'] < .005 and control['delta_relative_l2'] < .02, control
assert max(control['per_pair_delta_relative_l2']) < .02, control
meta['controls'] = control
meta['native_controls_sha256'] = sha(control_path)
print('NATIVE_CONTROL', json.dumps(control), flush=True)
(R / 'full-shards').mkdir(exist_ok=True)
ids = np.arange(a.rank, len(sequences), a.workers)
for start in range(0, len(ids), 4096):
    part = R / 'full-shards' / f'part-{a.workers}-{a.rank}-{start:06d}.npz'
    ix = ids[start:start + 4096]
    if part.exists():
        with np.load(part) as saved:
            assert str(saved['protocol_sha256']) == protocol_hash
            assert str(saved['script_sha256']) == meta['script_sha256']
            assert np.array_equal(saved['indices'], ix)
            assert saved['embeddings'].shape == (len(ix), 1024)
            assert np.isfinite(saved['embeddings']).all()
        continue
    chunks = []
    tic = time.monotonic()
    for k in range(0, len(ix), a.batch_size):
        chunks.append(extract(sequences[ix[k:k + a.batch_size]]))
    temp = part.with_suffix('.tmp.npz')
    np.savez(temp, indices=ix, embeddings=np.concatenate(chunks),
             protocol_sha256=protocol_hash, script_sha256=meta['script_sha256'])
    temp.replace(part)
    print('PROGRESS', a.rank, start + len(ix), len(ids), round(time.monotonic() - tic, 2), flush=True)
(R / f'FULL-COMPLETE-{a.rank:03d}.json').write_text(json.dumps(meta, indent=2) + '\n')
