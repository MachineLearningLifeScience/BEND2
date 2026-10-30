"""Complete CENO's frozen full-OpenSplice cache and run the original CPU readout.

No model selection or new preprocessing is introduced. All source inputs and
worker outputs are checked before the original crossvalidation CLI is called.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
import sklearn
from scipy.stats import spearmanr
from sklearn.model_selection import GroupKFold


def sha(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def merge(root):
    cpu = root / "cpu"
    source = cpu / "inputs"
    protocol = json.loads((root / "prepared/PROTOCOL.json").read_text())
    protocol_hash = sha(root / "prepared/PROTOCOL.json")
    assert sha(source / "canonical.parquet") == protocol["canonical_sha256"]
    assert sha(source / "cached-embeddings.npz") == protocol["cached_archive_sha256"]
    assert sha(root / "prepared/missing.parquet") == protocol["missing_sha256"]
    frame = pd.read_parquet(source / "canonical.parquet")
    assert len(frame) == 590104 and frame.gene_id.nunique() == 466
    assert frame.record_id.is_unique and frame.delta_y.notna().all()
    full = sorted(set(frame.sequence_ref) | set(frame.sequence_alt))
    assert len(full) == 590703
    lookup = {sequence: index for index, sequence in enumerate(full)}
    missing = pd.read_parquet(root / "prepared/missing.parquet").sequence.to_numpy()
    assert len(missing) == 307541 and len(set(missing)) == len(missing)
    completions = [json.loads(p.read_text()) for p in sorted(root.glob("COMPLETE-*.json"))]
    assert completions, "No completed inference workers"
    workers = completions[0]["workers"]
    assert len(completions) == workers
    assert sorted(c["rank"] for c in completions) == list(range(workers))
    for item in completions:
        assert item["workers"] == workers and item["protocol_sha256"] == protocol_hash
        assert item["model_revision"] == protocol["checkpoint_revision"]
        assert item["control"]["embedding_relative_l2"] < .005
        assert item["control"]["mutation_delta_relative_l2"] < .02
    assert len({c["model_weights_sha256"] for c in completions}) == 1
    assert len({c["script_sha256"] for c in completions}) == 1
    matrix = np.empty((len(full), 1024), dtype=np.float32)
    with np.load(source / "cached-embeddings.npz", allow_pickle=False) as cached:
        cached_sequences = cached["sequences"].astype(str)
        cached_features = cached["embeddings"]
        assert cached_features.shape == (283162, 1024)
        assert np.isfinite(cached_features).all()
        assert len(set(cached_sequences)) == len(cached_sequences)
        assert set(cached_sequences).isdisjoint(missing)
        assert set(cached_sequences) | set(missing) == set(full)
        cached_positions = np.array([lookup[s] for s in cached_sequences])
        matrix[cached_positions] = cached_features
        assert np.array_equal(matrix[cached_positions], cached_features)
    written = np.zeros(len(missing), dtype=bool)
    sources = {}
    shards = sorted((root / "shards").glob(f"part-{workers}-*.npz"))
    assert shards
    for path in shards:
        with np.load(path, allow_pickle=False) as shard:
            indices = shard["indices"]
            features = shard["embeddings"]
            assert str(shard["protocol_sha256"]) == protocol_hash
            assert indices.ndim == 1 and len(indices) == len(set(indices.tolist()))
            assert np.issubdtype(indices.dtype, np.integer)
            assert np.all((indices >= 0) & (indices < len(missing)))
            assert not written[indices].any()
            assert features.dtype == np.float32 and features.shape == (len(indices), 1024)
            assert np.isfinite(features).all()
            matrix[[lookup[s] for s in missing[indices]]] = features
            written[indices] = True
        sources[str(path.relative_to(root))] = sha(path)
    assert written.all() and np.isfinite(matrix).all()
    archive = cpu / "inputs/opensplice_ceno_full.npz"
    temporary = archive.with_suffix(".tmp.npz")
    np.savez(temporary, sequences=np.array(full), embeddings=matrix)
    temporary.replace(archive)
    metadata = {
        "model": "CladeTeam/CENO-1B-1m",
        "revision": protocol["checkpoint_revision"],
        "pooling": "mean_non_special_tokens",
        "embedding_dim": 1024,
        "projection": None,
        "n_sequences": len(full),
        "input": str(source / "canonical.parquet"),
        "input_sha256": protocol["canonical_sha256"],
        "archive_sha256": sha(archive),
        "cached_archive_sha256": protocol["cached_archive_sha256"],
        "cached_metadata": json.loads((source / "cached-embeddings.json").read_text()),
        "cache_preservation": "All 283162 cached rows copied exactly; 307541 new rows complete the canonical union.",
        "storage_dtype": str(matrix.dtype),
        "protocol_sha256": protocol_hash,
        "worker_metadata": completions,
        "shards_sha256": sources,
        "finalizer_sha256": sha(Path(__file__)),
    }
    write_json(archive.with_suffix(".json"), metadata)
    print("Merged", len(full), "unique sequences", flush=True)


def evaluate(root):
    from genomic_bending.cli import main

    cpu = root / "cpu"
    main([
        "crossval-intervention-embeddings",
        str(cpu / "inputs/canonical.parquet"),
        str(cpu / "inputs/opensplice_ceno_full.npz"),
        str(cpu / "results/opensplice_ceno_1b_1m_pretrained_gene_cv.json"),
        "--target", "delta_y", "--group-column", "gene_id", "--folds", "5", "--alpha", "10",
    ])


def audit(root):
    cpu = root / "cpu"
    path = cpu / "results/opensplice_ceno_1b_1m_pretrained_gene_cv.json"
    results = json.loads(path.read_text())
    prediction_path = path.with_suffix(".predictions.parquet")
    predictions = pd.read_parquet(prediction_path)
    source = pd.read_parquet(cpu / "inputs/canonical.parquet")
    assert len(predictions) == len(source) == 590104
    assert predictions.gene_id.nunique() == 466
    assert np.array_equal(predictions.record_id.to_numpy(), source.record_id.to_numpy())
    assert np.array_equal(predictions.gene_id.to_numpy(), source.gene_id.to_numpy())
    assert np.array_equal(predictions.y_true.to_numpy(), source.delta_y.to_numpy())
    assert np.isfinite(predictions[["y_true", "y_pred"]].to_numpy()).all()
    for fold, (train, test) in enumerate(GroupKFold(5).split(source, groups=source.gene_id.astype(str))):
        assert set(source.iloc[train].gene_id).isdisjoint(source.iloc[test].gene_id)
        assert np.all(predictions.iloc[test].fold.to_numpy() == fold)
    rows = []
    for gene, group in predictions.groupby("gene_id", sort=True):
        value = float(spearmanr(group.y_true, group.y_pred).statistic)
        rows.append({"gene_id": gene, "spearman": value, "n": len(group)})
    per_gene = pd.DataFrame(rows)
    valid = per_gene.spearman.dropna().to_numpy()
    independent_mean = float(valid.mean())
    rng = np.random.default_rng(20260822)
    interval = np.quantile(rng.choice(valid, size=(2000, len(valid)), replace=True).mean(axis=1), [.025, .975])
    np.testing.assert_allclose(independent_mean, results["macro_spearman"], atol=1e-12, rtol=0)
    np.testing.assert_allclose(interval, results["macro_spearman_ci95"], atol=1e-12, rtol=0)
    assert results["n_groups"] == 466 and results["n_records"] == 590104
    per_gene.to_csv(cpu / "results/opensplice_ceno_1b_1m.per_gene.csv", index=False)
    package = Path(sys.modules["genomic_bending"].__file__).parent
    files = ["cli.py", "models/embeddings.py", "eval/metrics.py", "eval/bootstrap.py"]
    report = {
        "status": "passed",
        "canonical_sha256": sha(cpu / "inputs/canonical.parquet"),
        "embedding_archive_sha256": sha(cpu / "inputs/opensplice_ceno_full.npz"),
        "predictions_sha256": sha(prediction_path),
        "result_sha256": sha(path),
        "implementation_sha256": {name: sha(package / name) for name in files},
        "n_records": 590104, "n_genes": 466,
        "n_correlation_eligible_genes": len(valid),
        "macro_spearman": independent_mean,
        "ci95": interval.tolist(),
        "bootstrap": {"replicates": 2000, "seed": 20260822, "unit": "gene", "type": "percentile"},
        "features": "ALT−REF float32 embeddings + sequence length difference + train-fitted context and intervention-type one-hot encoders",
        "regressor": "Ridge(alpha=10,solver=lsqr,fit_intercept=True); no scaling or normalization",
        "folds": "GroupKFold(5),gene_id.astype(str),no shuffle; exactly replayed",
        "target": "raw delta_y; all SNVs and deletions",
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__, "scipy": scipy.__version__, "sklearn": sklearn.__version__},
    }
    write_json(cpu / "results/AUDIT.json", report)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--stage", choices=["all", "merge", "evaluate", "audit"], default="all")
    args = parser.parse_args()
    if args.stage in {"all", "merge"}:
        merge(args.root)
    if args.stage in {"all", "evaluate"}:
        evaluate(args.root)
    if args.stage in {"all", "audit"}:
        audit(args.root)
