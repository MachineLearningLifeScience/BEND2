#!/usr/bin/env python3
"""Validate the native Evo2 cache, fit the fixed GTEx readout, bootstrap and audit.

Run from anywhere; all default paths are relative to this handoff package.
This script never downloads data, launches a GPU job or changes an extraction.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import time
import numpy as np

PACKAGE = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
EXPECTED_COUNTS = 'ed030943a78e7a5a8273fd6aa4883729b044be292f87c7cf90afb96f7ea81555'
EXPECTED_PAIRS = 'cedfda3740844e59fe04d342704c0185ae3302f6a994a6d63a71f384a0ea9ba3'
EXPECTED_DATA = {
    'targets.npz': 'be027fb017d6d184759ae098bcac00fbc23ad73699203a6f0f28ad6269ed1a0b',
    'native_predictions.npz': '3560557398abb082eb47800c7c611927cd0de15a28c0fc54239b6019a0209c47',
}

def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def link(dst, src):
    src = src.resolve(strict=True)
    if dst.is_symlink():
        if dst.resolve() != src:
            raise ValueError(f'Existing link points elsewhere: {dst}')
    elif dst.exists():
        raise ValueError(f'Refusing to replace existing path: {dst}')
    else:
        dst.symlink_to(src)

def validate_data(data):
    for name, expected in EXPECTED_DATA.items():
        actual = sha256(data / 'prepared' / name)
        if actual != expected:
            raise ValueError(f'Wrong prepared {name}: {actual}')
    if sha256(data / 'bootstrap/bootstrap_counts.npy') != EXPECTED_COUNTS:
        raise ValueError('Bootstrap counts do not match the original 10,000 paired draws')
    if sha256(data / 'bootstrap/pairs.npz') != EXPECTED_PAIRS:
        raise ValueError('Contrast partner choices do not match the original fixed pairs')
    D = np.load(data / 'prepared/targets.npz')
    N = np.load(data / 'prepared/native_predictions.npz')
    tr, va, te = D['train'], D['validation'], N['global_indices']
    assert D['truth'].shape == (19282, 51)
    assert (len(tr), len(va), len(te)) == (12146, 1350, 5782)
    assert len(D['test']) == 5786
    np.testing.assert_array_equal(np.sort(np.concatenate([tr, va, D['test']])), np.arange(19282))
    assert len(np.setdiff1d(D['test'], te)) == 4
    assert not np.setdiff1d(te, D['test']).size
    assert len(np.unique(np.concatenate([tr, va, te]))) == 19278
    assert not np.intersect1d(tr, va).size
    assert not np.intersect1d(np.concatenate([tr, va]), te).size
    np.testing.assert_array_equal(D['gene_ids'][te], N['gene_ids'])
    np.testing.assert_array_equal(D['tissues'], N['tissues'])
    np.testing.assert_array_equal(D['truth'][te], N['truth'])
    counts = np.load(data / 'bootstrap/bootstrap_counts.npy', mmap_mode='r')
    assert counts.shape == (10000, 5782) and counts.dtype == np.uint16
    assert np.all(counts.sum(axis=1) == 5782)
    pairs = np.load(data / 'bootstrap/pairs.npz')
    np.testing.assert_array_equal(pairs['genes'], N['gene_ids'])
    np.testing.assert_array_equal(pairs['tissues'], N['tissues'])
    print('Original data, holdouts and paired bootstrap verified.', flush=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=PACKAGE / 'data')
    parser.add_argument('--producer', type=Path, default=PACKAGE / 'run/extraction')
    parser.add_argument('--output', type=Path, default=PACKAGE / 'run/final_evaluation')
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--wait', action='store_true', help='Wait quietly for producer/COMPLETE.json (otherwise fail if incomplete)')
    parser.add_argument('--validate-data', action='store_true', help='Verify bundled targets/split/bootstrap and exit; no complete embeddings required')
    args = parser.parse_args()
    if args.workers < 1:
        parser.error('--workers must be positive')
    data, producer, out = args.data_dir.resolve(), args.producer.resolve(), args.output.resolve()
    validate_data(data)
    if args.validate_data:
        return
    marker = producer / 'COMPLETE.json'
    if not marker.exists() and not args.wait:
        parser.error(f'{marker} is absent. Finish native extraction first, or use --wait.')
    if not marker.exists():
        print(f'Waiting for {marker}', flush=True)
    while not marker.exists():
        time.sleep(60)
    complete = json.loads(marker.read_text())
    protocol = json.loads((producer / 'protocol.json').read_text())
    embeddings = np.load(producer / 'embeddings.npy', mmap_mode='r')
    mask = np.load(producer / 'completed.npy')
    assert embeddings.shape == (19282, 512) and np.isfinite(embeddings).all()
    assert mask.shape == (19282,) and mask.all()
    assert protocol['native_fp8'] is True and protocol['window_length'] == 131072
    assert protocol['representation_unchanged'] is True
    embedding_hash = sha256(producer / 'embeddings.npy')
    assert embedding_hash == complete['embedding_sha256'], 'Embedding hash does not match producer completion'
    out.mkdir(parents=True, exist_ok=True)
    link(out / 'prepared', data / 'prepared')
    (out / 'evo2').mkdir(exist_ok=True)
    link(out / 'evo2/embeddings.npy', producer / 'embeddings.npy')
    link(out / 'evo2/complete.json', marker)
    (out / 'evo2_20b').mkdir(exist_ok=True)
    link(out / 'evo2_20b/features.npy', producer / 'embeddings.npy')
    (out / 'evaluation').mkdir(exist_ok=True)
    for name in ['bootstrap_counts.npy', 'pairs.npz']:
        link(out / 'evaluation' / name, data / 'bootstrap' / name)
    commands = [
        ('fit_gtex_ridge.py', ['--model', 'evo2_20b']),
        ('evaluate_evo2.py', ['--workers', str(args.workers), '--replicates', '10000']),
        ('independent_audit.py', ['--models', 'evo2_20b']),
    ]
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    for script, extra in commands:
        print(f'Running {script}', flush=True)
        subprocess.run([sys.executable, str(SCRIPTS / script), '--run', str(out), *extra], env=env, check=True)
    result = json.loads((out / 'independent-audit.json').read_text())
    outputs = ['evo2_20b/predictions.npz', 'evo2_20b/fit.npz', 'evo2_20b/protocol.json',
               'evo2_20b/retrieval_confusion.csv', 'evaluation/results.csv',
               'evaluation/evo2_20b_bootstrap.npz', 'evaluation/protocol.json', 'independent-audit.json']
    final = dict(
        finished_unix=time.time(), producer_embedding_sha256=embedding_hash,
        bootstrap_counts_sha256=EXPECTED_COUNTS, contrast_pairs_sha256=EXPECTED_PAIRS, independent_audit=result,
        packages={name: importlib.metadata.version(name) for name in ['numpy', 'scipy', 'scikit-learn', 'pandas', 'numba']},
        output_sha256={name: sha256(out / name) for name in outputs},
        scripts_sha256={path.name: sha256(path) for path in sorted(SCRIPTS.glob('*.py'))},
    )
    temp = out / 'COMPLETE.json.tmp'
    temp.write_text(json.dumps(final, indent=2) + '\n')
    temp.replace(out / 'COMPLETE.json')
    print('Evaluation and independent audit complete.', flush=True)
    print((out / 'evaluation/results.csv').read_text(), flush=True)

if __name__ == '__main__':
    main()
