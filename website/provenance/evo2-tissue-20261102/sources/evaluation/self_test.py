#!/usr/bin/env python3
"""Fast CPU checks using synthetic data only; never produces benchmark results."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import numpy as np
from scipy.stats import rankdata, spearmanr
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from gtex_metrics import validate, retrieval, ordering, ranks_matrix

scripts = Path(__file__).resolve().parent
validate()  # Weighted-rank kernels vs explicitly duplicated SciPy rows, including ties.
rng = np.random.default_rng(20260923)
P = rng.normal(size=(45, 7))
Y = rng.normal(size=(45, 7))
counts = rng.multinomial(45, np.full(45, 1 / 45)).astype(np.uint16)
W, _ = ranks_matrix([ordering(P[:, j]) for j in range(7)], counts)
T, _ = ranks_matrix([ordering(Y[:, j]) for j in range(7)], counts)
sample = np.repeat(np.arange(45), counts)
independent = np.array([[spearmanr(P[sample, i], Y[sample, j]).statistic for j in range(7)] for i in range(7)])
np.testing.assert_allclose(W.T @ T, independent, atol=1e-12, rtol=0)
winners = np.isclose(independent, independent.max(axis=1)[:, None], atol=1e-12, rtol=0)
score = np.mean(np.diag(winners) / winners.sum(axis=1))
np.testing.assert_allclose(retrieval(W, T), score, atol=1e-12)
# All predicted profiles identical: every query receives fractional tied credit.
flat = np.tile(T[:, :1], (1, 7))
np.testing.assert_allclose(retrieval(flat, flat), 1 / 7, atol=1e-12)

with tempfile.TemporaryDirectory(prefix='cpu-self-test-', dir=scripts) as temporary:
    root = Path(temporary)
    (root / 'prepared').mkdir()
    (root / 'evo2').mkdir()
    X = rng.normal(size=(100, 12)).astype(np.float32)
    truth = X @ rng.normal(size=(12, 9)) + rng.normal(size=(100, 9))
    train, val = np.arange(65), np.arange(65, 80)
    np.savez(root / 'prepared/targets.npz', train=train, validation=val, truth=truth,
             gene_ids=np.array([f'gene{i}' for i in range(100)]), tissues=np.array([f't{i}' for i in range(9)]))
    (root / 'prepared/protocol.json').write_text('{}\n')
    np.save(root / 'evo2/embeddings.npy', X)
    (root / 'evo2/complete.json').write_text('{}\n')
    env = dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    subprocess.run([sys.executable, str(scripts / 'fit_gtex_ridge.py'), '--run', str(root), '--model', 'evo2_20b'], env=env, check=True, stdout=subprocess.DEVNULL)
    observed = np.load(root / 'evo2_20b/predictions.npz')['predictions']
    protocol = json.loads((root / 'evo2_20b/protocol.json').read_text())
    xs = StandardScaler().fit(X.astype(np.float64)[train])
    ys = StandardScaler().fit(truth[train])
    best = None
    for alpha in [10000., 1000., 100., 10., 1., .1]:
        model = Ridge(alpha=alpha, fit_intercept=False, solver='cholesky').fit(xs.transform(X[train]), ys.transform(truth[train]))
        mse = np.mean((model.predict(xs.transform(X[val])) - ys.transform(truth[val])) ** 2)
        if best is None or mse < best[0] - 1e-12:
            best = mse, alpha, model
    assert protocol['alpha'] == best[1]
    expected = ys.inverse_transform(best[2].predict(xs.transform(X)))
    # Reuse float64 casting from the production extraction-to-ridge path.
    X64 = X.astype(np.float64)
    xs = StandardScaler().fit(X64[train])
    exact = Ridge(alpha=best[1], fit_intercept=False, solver='cholesky').fit(xs.transform(X64[train]), ys.transform(truth[train]))
    expected = ys.inverse_transform(exact.predict(xs.transform(X64)))
    np.testing.assert_allclose(observed, expected, atol=1e-10, rtol=1e-10)
    maximum_error = float(np.max(np.abs(observed - expected)))

print(json.dumps(dict(status='passed',
    checks=['weighted ranks versus explicit resampling', 'independent SciPy cross-tissue correlations',
            'fractional retrieval ties', 'ridge alpha selection', 'eigendecomposition versus sklearn Cholesky predictions'],
    synthetic_ridge_prediction_max_abs_error=maximum_error), indent=2))
