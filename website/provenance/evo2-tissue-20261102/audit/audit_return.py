"""Independently replay the collaborator's native-FP8 Evo2 result on frozen GTEx data.

No returned Python code is executed. Does not edit the returned package or paper.
"""
from pathlib import Path
import csv
import hashlib
import json
import zipfile
import numpy as np
import scipy
from scipy.linalg import solve
from scipy.stats import rankdata, spearmanr

ROOT = Path(__file__).resolve().parent
RETURN = ROOT / 'evo2-results'
PACKET = ROOT.parent / 'evo2-collaborator-handoff-stopped-20260923/evo2-gtex-handoff'
DATA = PACKET / 'data'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read_json(path):
    return json.loads(path.read_text())

with zipfile.ZipFile('/Users/fvk220/Downloads/evo2-results.zip') as archive:
    assert archive.testzip() is None

manifest = read_json(RETURN / 'RETURN_MANIFEST.json')
for item in manifest['files']:
    path = RETURN / item['path']
    assert path.stat().st_size == item['bytes']
    assert sha(path) == item['sha256'], item['path']
prepared_protocol = read_json(DATA / 'prepared/protocol.json')
for name, expected in prepared_protocol['data_hashes'].items():
    path = DATA / 'prepared' / name
    if name != 'sequences.npy':
        assert sha(path) == expected, name
assert sha(DATA / 'bootstrap/bootstrap_counts.npy') == 'ed030943a78e7a5a8273fd6aa4883729b044be292f87c7cf90afb96f7ea81555'
assert sha(DATA / 'bootstrap/pairs.npz') == 'cedfda3740844e59fe04d342704c0185ae3302f6a994a6d63a71f384a0ea9ba3'
complete = read_json(RETURN / 'final_evaluation/COMPLETE.json')
script_checks = {}
for name, expected in complete['scripts_sha256'].items():
    script_checks[name] = sha(PACKET / 'scripts/evaluation' / name) == expected
for name, expected in complete['output_sha256'].items():
    assert sha(RETURN / 'final_evaluation' / name) == expected, name
protocol = read_json(RETURN / 'extraction/protocol.json')
assert protocol['source_sequences_sha256'] == prepared_protocol['data_hashes']['sequences.npy']
assert protocol['checkpoint_sha256'] == '979b345dc700a9cae6b63f570d9b3f438e31a68dd8dc0bc0d8d2a0fcd3caf791'
assert sha(RETURN / 'extraction/run_evo2_local.py') == protocol['script_sha256']
assert sha(RETURN / 'extraction/multi_gpu_state.py') == protocol['state_adapter_sha256']
assert protocol['native_fp8'] is True and protocol['representation_unchanged'] is True
assert all(script_checks.values()), script_checks
assert sha(RETURN / 'extraction/embeddings.npy') == complete['producer_embedding_sha256']

D = np.load(DATA / 'prepared/targets.npz')
N = np.load(DATA / 'prepared/native_predictions.npz')
Z = np.load(RETURN / 'final_evaluation/evo2_20b/predictions.npz')
F = np.load(RETURN / 'final_evaluation/evo2_20b/fit.npz')
E = np.load(RETURN / 'extraction/embeddings.npy')
done = np.load(RETURN / 'extraction/completed.npy')
assert E.shape == (19282, 512) and E.dtype == np.float16
assert done.shape == (19282,) and done.dtype == bool and done.all()
assert np.isfinite(E).all() and np.all(np.any(E != 0, axis=1))
X = E.astype(np.float64)
Y = D['truth'].astype(np.float64)
tr, va, te = D['train'], D['validation'], N['global_indices']
assert (len(tr), len(va), len(te)) == (12146, 1350, 5782)
np.testing.assert_array_equal(np.sort(np.r_[tr, va, D['test']]), np.arange(len(X)))
assert not np.intersect1d(np.r_[tr, va], te).size
np.testing.assert_array_equal(D['gene_ids'], Z['gene_ids'])
np.testing.assert_array_equal(D['gene_ids'][te], N['gene_ids'])
np.testing.assert_array_equal(D['tissues'], Z['tissues'])
np.testing.assert_array_equal(D['tissues'], N['tissues'])
np.testing.assert_array_equal(Y[te], N['truth'])
assert Y.shape == Z['predictions'].shape == (19282, 51)

# Independent training-only standardization and direct positive-definite solve.
xmean, xscale = X[tr].mean(0), X[tr].std(0)
ymean, yscale = Y[tr].mean(0), Y[tr].std(0)
xscale[xscale == 0] = 1
yscale[yscale == 0] = 1
Xt, Yt = (X[tr] - xmean) / xscale, (Y[tr] - ymean) / yscale
Xv, Yv = (X[va] - xmean) / xscale, (Y[va] - ymean) / yscale
gram, cross = Xt.T @ Xt, Xt.T @ Yt
validation, best = [], None
for alpha in [10000., 1000., 100., 10., 1., .1]:
    coef = solve(gram + alpha * np.eye(512), cross, assume_a='pos')
    loss = float(np.mean((Xv @ coef - Yv) ** 2))
    validation.append(dict(alpha=alpha, validation_standardized_mse=loss))
    if best is None or loss < best[0] - 1e-12:
        best = loss, alpha, coef
assert best[1] == float(F['alpha']) == 1.
pred = ((X - xmean) / xscale @ best[2]) * yscale + ymean
prediction_error = float(np.max(np.abs(pred - Z['predictions'])))
assert prediction_error < 1e-6
for key, value in [('feature_mean', xmean), ('feature_scale', xscale),
                   ('target_mean', ymean), ('target_scale', yscale), ('coef', best[2])]:
    np.testing.assert_allclose(F[key], value, atol=1e-7, rtol=1e-8)
P, truth = Z['predictions'][te], Y[te]

def retrieval(p, y, matrix=False):
    a, b = rankdata(p, axis=0), rankdata(y, axis=0)
    a -= a.mean(0)
    b -= b.mean(0)
    corr = (a / np.linalg.norm(a, axis=0)).T @ (b / np.linalg.norm(b, axis=0))
    wins = np.isclose(corr, corr.max(1)[:, None], atol=1e-12, rtol=0)
    value = float(np.mean(np.diag(wins) / wins.sum(1)))
    return (value, corr, wins) if matrix else value

pairs = np.load(DATA / 'bootstrap/pairs.npz')
delta_p = [np.take_along_axis(P, pairs[k], axis=1) - P for k in ['maximum', 'random']]
delta_y = [np.take_along_axis(truth, pairs[k], axis=1) - truth for k in ['maximum', 'random']]
score, corr, wins = retrieval(P, truth, matrix=True)
point = [float(spearmanr(a.ravel(), b.ravel()).statistic) for a, b in zip(delta_p, delta_y)] + [score]
rows = list(csv.DictReader((RETURN / 'final_evaluation/evaluation/results.csv').open()))
metrics = ['maximum_contrast_spearman', 'random_contrast_spearman', 'retrieval_top1']
rows = {r['metric']: r for r in rows}
B = np.load(RETURN / 'final_evaluation/evaluation/evo2_20b_bootstrap.npz')
draws = B['draws']
assert draws.shape == (10000, 3) and np.isfinite(draws).all()
assert np.all(B['constant_profiles'] == 0)
summaries = []
for j, metric in enumerate(metrics):
    row = rows[metric]
    assert abs(point[j] - float(row['value'])) < 1e-12
    lo, hi = np.percentile(draws[:, j], [2.5, 97.5])
    np.testing.assert_allclose([lo, hi], [float(row['low']), float(row['high'])], rtol=0, atol=1e-12)
    assert int(row['invalid_replicates']) == 0
    summaries.append(dict(metric=metric, value=point[j], low=float(lo), high=float(hi)))
counts = np.load(DATA / 'bootstrap/bootstrap_counts.npy', mmap_mode='r')
assert counts.shape == (10000, 5782) and np.all(counts.sum(1) == 5782)
# Preselected random draws, plus quantile/extreme draws; use explicitly duplicated
# rows and SciPy ranking, independently of the handoff's weighted-rank kernels.
chosen = np.unique(np.r_[0, 1, 9999, np.random.default_rng(20261031).choice(10000, 24, replace=False),
                        np.argmin(draws, axis=0), np.argmax(draws, axis=0)])
boot_errors = []
for index in chosen:
    sample = np.repeat(np.arange(len(te)), counts[index])
    values = [float(spearmanr(a[sample].ravel(), b[sample].ravel()).statistic)
              for a, b in zip(delta_p, delta_y)] + [retrieval(P[sample], truth[sample])]
    error = float(np.max(np.abs(np.asarray(values) - draws[index])))
    assert error < 1e-12, (int(index), values, draws[index])
    boot_errors.append(error)
    print('replayed bootstrap', int(index), flush=True)

confusion = np.loadtxt(RETURN / 'final_evaluation/evo2_20b/retrieval_confusion.csv', delimiter=',', skiprows=1, usecols=range(1, 52))
np.testing.assert_allclose(corr, confusion, atol=1e-12, rtol=0)
correct_tissues = [str(D['tissues'][j]) for j in range(51) if wins[j, j]]
report = dict(
    date='2026-11-02', status='passed_numerical_replay',
    source_zip='/Users/fvk220/Downloads/evo2-results.zip',
    source_zip_sha256=sha(Path('/Users/fvk220/Downloads/evo2-results.zip')),
    manifest_files_verified=len(manifest['files']), original_evaluation_scripts_match=script_checks,
    embedding_shape=list(E.shape), all_genes_complete=True, finite_and_nonzero_rows=True,
    n_train=len(tr), n_validation=len(va), n_test=len(te), n_tissues=51,
    exact_gene_and_tissue_order=True, no_test_index_fit_overlap=True,
    selected_alpha=best[1], validation=validation, max_prediction_error=prediction_error,
    results=summaries, bootstrap_replicates=10000,
    bootstrap_independent_expanded_replays=len(chosen),
    bootstrap_indices=chosen.tolist(), bootstrap_max_replay_error=max(boot_errors),
    confidence_intervals_recomputed_from_all_returned_draws=True,
    correct_tissues=correct_tissues, random_tissue_id_percent=100/51,
    precision='native FP8, original snapshot continued across two H100 GPUs',
    extraction_audit='See extraction-review.md for independent model-use review',
    limitations=[
        'GPU inference was not rerun locally; extraction was reviewed separately from this CPU audit.',
        'Confidence intervals resample held-out genes, not donors or tissues.',
        'The inherited split includes eight held-out pseudoautosomal windows identical to train/validation windows; this is common to the supplied evaluation.'
    ],
    runtime=dict(numpy=np.__version__, scipy=scipy.__version__),
)
(ROOT / 'independent-replay.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
