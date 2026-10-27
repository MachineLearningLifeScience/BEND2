"""DNABERT2 single-base probability query with a fixed tokenization boundary.

The target is removed before tokenization. Left and right visible DNA are BPE
tokenized independently; one MASK token replaces the one missing nucleotide.
This is an explicit new query interface, not native whole-BPE-token masking.
No model parameters, calibration or query settings use evaluation labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import transformers
from transformers import AutoModelForMaskedLM, AutoTokenizer

REV = "b5d88cda421f106afef78cd286200a5b5b8f6fea"
MODEL = Path("/scratch/project_465003339/ajeppese/gimbench-gtex-extra-20260923/extra-models-direct/models--zhihan1996--DNABERT-2-117M/snapshots") / REV
PANEL_SHA = "d4a07c4bcb98c4f5a3f94a6d82a3dfd5e01b3b5baedfc5efa075fe75e3f871f1"
BASES = "ACGT"


def sha(path):
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def prepare(root):
    assert sha(root / "windows.parquet") == PANEL_SHA
    table = pd.read_parquet(root / "windows.parquet")
    table = table.query('split == "evaluation"').reset_index(drop=True)
    assert len(table) == 512 and table.window_id.is_unique
    # Check the original genomic block column rather than treating correlated
    # windows as independent bootstrap units.
    block_col = next(k for k in ["block_id", "block"] if k in table)
    assert table[block_col].nunique() == len(table)
    tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True, local_files_only=True)
    bases = [tok.encode(base, add_special_tokens=False) for base in BASES]
    assert all(len(x) == 1 for x in bases), bases
    base_ids = [x[0] for x in bases]
    assert len(set(base_ids)) == 4
    assert tok.convert_ids_to_tokens(base_ids) == list(BASES)
    # Generic PreTrainedTokenizerFast.build_inputs_with_special_tokens does not
    # apply this tokenizer's backend postprocessor. Check its native encoding
    # and reproduce exactly that single CLS/SEP pair around the full query.
    for example in ["A", "ACGT", "ACGT" * 100, tok.mask_token]:
        assert tok.encode(example, add_special_tokens=True) == [tok.cls_token_id] + tok.encode(example, add_special_tokens=False) + [tok.sep_token_id]
    max_model_tokens = json.loads((MODEL / "config.json").read_text())["max_position_embeddings"]
    assert max_model_tokens == 512

    def query(sequence):
        assert len(sequence) == 1200 and set(sequence) <= set(BASES)
        left = tok.encode(sequence[:600], add_special_tokens=False)
        right = tok.encode(sequence[601:], add_special_tokens=False)
        assert "".join(tok.convert_ids_to_tokens(left)) == sequence[:600]
        assert "".join(tok.convert_ids_to_tokens(right)) == sequence[601:]
        assert not (set(left + right) & set(tok.all_special_ids))
        result = [tok.cls_token_id] + left + [tok.mask_token_id] + right + [tok.sep_token_id]
        assert result.count(tok.mask_token_id) == 1
        assert len(result) <= max_model_tokens, (len(result), "No truncation permitted")
        return result

    queries, positions, lengths = [], [], []
    for sequence in table.sequence:
        ids = query(sequence)
        # This explicitly checks input invariance for every possible target base.
        for base in BASES:
            assert query(sequence[:600] + base + sequence[601:]) == ids
        queries.append(ids)
        positions.append(ids.index(tok.mask_token_id))
        lengths.append(len(ids))
    width = max(lengths)
    ids = np.full((len(table), width), tok.pad_token_id, dtype=np.int64)
    attention = np.zeros_like(ids)
    for i, tokens in enumerate(queries):
        ids[i, :len(tokens)] = tokens
        attention[i, :len(tokens)] = 1
    np.savez(root / "queries.npz", input_ids=ids, attention_mask=attention,
             mask_positions=np.array(positions), token_lengths=np.array(lengths),
             base_ids=np.array(base_ids), window_ids=table.window_id.to_numpy(dtype=str))
    protocol = dict(query_name="fixed-boundary single-base query", model="zhihan1996/DNABERT-2-117M",
                    revision=REV, target_position_zero_based=600, nucleotide_window=1200,
                    visible_bases=1199, n_windows=len(table), independent_genomic_blocks=512,
                    block_column=block_col, query="CLS + BPE(left visible DNA) + MASK + BPE(right visible DNA) + SEP",
                    token_range=[min(lengths), max(lengths)], max_allowed_tokens=max_model_tokens,
                    nucleotide_ids=dict(zip(BASES, base_ids)), conditional_probability="Softmax of pretrained MASK logits restricted to the four single-nucleotide tokens",
                    full_vocabulary_mass="Retained as a diagnostic before four-way renormalization",
                    weights_and_computation="FP32; TF32 disabled; original eager attention, legacy flash path disabled",
                    truncation=False, target_substitution_invariance_checks=512*4,
                    query_selection="Fixed before evaluating; no calibration, fitting or label-driven selection",
                    bootstrap_replicates=4000, bootstrap_seed=20260910,
                    bootstrap_unit="one window per independent 1 Mb genomic block",
                    bootstrap_sampling="multinomial with replacement, original prior benchmark convention",
                    panel_sha256=PANEL_SHA, original_protocol_sha256=sha(root / "original-prior-protocol.json"),
                    queries_sha256=sha(root / "queries.npz"), script_sha256=sha(__file__),
                    tokenizer_files={p.name: sha(p) for p in MODEL.glob("*json")},
                    model_source_files={p.name: sha(p) for p in MODEL.glob("*.py")})
    save(root / "PROTOCOL.json", protocol)
    print(json.dumps(protocol, indent=2), flush=True)


def evaluate(root, pilot):
    protocol = json.loads((root / "PROTOCOL.json").read_text())
    assert protocol["script_sha256"] == sha(__file__)
    assert protocol["panel_sha256"] == sha(root / "windows.parquet")
    assert protocol["queries_sha256"] == sha(root / "queries.npz")
    torch.set_num_threads(6)
    torch.manual_seed(20260910)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    assert torch.cuda.is_available()
    model, loading = AutoModelForMaskedLM.from_pretrained(
        MODEL, trust_remote_code=True, local_files_only=True, torch_dtype=torch.float32,
        use_safetensors=True, output_loading_info=True)
    assert not any(loading.get(k) for k in ["missing_keys", "mismatched_keys", "error_msgs"]), loading
    assert not loading.get("unexpected_keys"), loading
    assert model.__class__.__name__ == "BertForMaskedLM"
    assert hasattr(model, "cls") and hasattr(model.cls, "predictions")
    module = sys.modules[model.__class__.__module__]
    assert hasattr(module, "flash_attn_qkvpacked_func")
    module.flash_attn_qkvpacked_func = None
    model = model.cuda().eval().requires_grad_(False)
    assert {p.dtype for p in model.parameters()} == {torch.float32}
    data = np.load(root / "queries.npz", allow_pickle=False)
    base_ids = torch.tensor(data["base_ids"], device="cuda")

    @torch.inference_mode()
    def predict(indices, trim=True):
        width = int(data["token_lengths"][indices].max()) if trim else data["input_ids"].shape[1]
        ids = torch.tensor(data["input_ids"][indices, :width], device="cuda")
        attention = torch.tensor(data["attention_mask"][indices, :width], device="cuda")
        outputs = model(input_ids=ids, attention_mask=attention, token_type_ids=torch.zeros_like(ids))
        logits = outputs.logits
        assert logits.dtype == torch.float32 and torch.isfinite(logits).all()
        selected = logits[torch.arange(len(indices), device="cuda"), torch.tensor(data["mask_positions"][indices], device="cuda")].double()
        base_logits = selected[:, base_ids]
        log_prob = torch.log_softmax(base_logits, dim=-1)
        log_mass = torch.logsumexp(base_logits, dim=-1) - torch.logsumexp(selected, dim=-1)
        return log_prob.cpu().numpy(), log_mass.cpu().numpy()

    started = time.monotonic()
    indices = np.array([0, 1, 2, 3, int(np.argmin(data["token_lengths"])), int(np.argmax(data["token_lengths"]))])
    batch, batch_mass = predict(indices)
    individual = np.concatenate([predict(np.array([i]))[0] for i in indices])
    padded, padded_mass = predict(indices, trim=False)
    check = dict(max_batch_individual_log_probability_difference=float(np.max(np.abs(batch-individual))),
                 max_padded_log_probability_difference=float(np.max(np.abs(batch-padded))),
                 max_padded_log_vocabulary_mass_difference=float(np.max(np.abs(batch_mass-padded_mass))))
    assert max(check.values()) < 1e-4, check
    metadata = dict(protocol_sha256=sha(root / "PROTOCOL.json"), checkpoint_revision=REV,
                    checkpoint_sha256=sha(MODEL / "model.safetensors"), script_sha256=sha(__file__),
                    loading_info=loading, checks=check, torch=torch.__version__, transformers=transformers.__version__,
                    numpy=np.__version__, python=platform.python_version(), gpu=torch.cuda.get_device_name(0),
                    parameters=sum(p.numel() for p in model.parameters()))
    if pilot:
        save(root / "pilot.json", dict(**metadata, seconds=time.monotonic()-started, pilot_windows=indices.tolist()))
        print("PILOT_PASS", json.dumps(check), flush=True)
        return
    prior_pilot = json.loads((root / "pilot.json").read_text())
    assert prior_pilot["protocol_sha256"] == metadata["protocol_sha256"]
    assert prior_pilot["checkpoint_sha256"] == metadata["checkpoint_sha256"]
    values, masses = [], []
    for start in range(0, 512, 16):
        probabilities, log_mass = predict(np.arange(start, min(start+16, 512)))
        values.append(probabilities)
        masses.append(log_mass)
    logp, logmass = np.concatenate(values), np.concatenate(masses)
    assert logp.shape == (512, 4) and np.isfinite(logp).all() and np.isfinite(logmass).all()
    np.testing.assert_allclose(np.exp(logp).sum(1), 1, atol=1e-12)
    table = pd.read_parquet(root / "windows.parquet").query('split == "evaluation"').reset_index(drop=True)
    truth = np.array([BASES.index(s[600]) for s in table.sequence])
    out = table.drop(columns="sequence").copy()
    for i, base in enumerate(BASES):
        out[f"p_{base}"] = np.exp(logp[:, i])
        out[f"log_p_{base}"] = logp[:, i]
    top = logp == logp.max(axis=1, keepdims=True)
    out["true_base"] = [BASES[t] for t in truth]
    out["token_count"] = data["token_lengths"]
    out["full_vocabulary_base_mass"] = np.exp(logmass)
    out["log_full_vocabulary_base_mass"] = logmass
    out["recovery_bits"] = -logp[np.arange(512), truth]/np.log(2)
    out["recovery_accuracy"] = top[np.arange(512), truth]/top.sum(axis=1)
    out.to_parquet(root / "predictions.parquet", index=False)
    out.to_csv(root / "predictions.csv", index=False)
    weights = np.random.default_rng(20260910).multinomial(512, np.full(512, 1/512), 4000)
    summary = {}
    for column in ["recovery_bits", "recovery_accuracy"]:
        v = out[column].to_numpy()
        ci = np.quantile(weights @ v / 512, [0.025, 0.975])
        summary[column] = float(v.mean())
        summary[column+"_low"], summary[column+"_high"] = map(float, ci)
    summary["n_windows"] = 512
    summary["vocabulary_mass_quantiles"] = {str(q): float(np.quantile(np.exp(logmass), q)) for q in [0,.05,.25,.5,.75,.95,1]}
    save(root / "RESULT.json", dict(**metadata, summary=summary,
         predictions_sha256=sha(root / "predictions.parquet"), seconds=time.monotonic()-started))
    print("COMPLETE", json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--stage", choices=["prepare", "pilot", "evaluate"], required=True)
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare(args.root)
    else:
        evaluate(args.root, args.stage == "pilot")
