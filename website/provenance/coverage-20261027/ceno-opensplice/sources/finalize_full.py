"""Merge a uniformly recomputed CENO archive, then run the unchanged readout.

The historical CUDA cache is deliberately not read by this finalizer.
"""
from pathlib import Path
import argparse,json
import numpy as np
import pandas as pd
from finalize import sha, write_json, evaluate, audit
from readout_checks import capture_lsqr, verify_archived_folds, solver_sensitivity
from release_summary import build_summary


def merge(root):
    protocol_path=root/'prepared/FULL_PROTOCOL.json'
    protocol=json.loads(protocol_path.read_text())
    protocol_hash=sha(protocol_path)
    canonical=root/'cpu/inputs/canonical.parquet'
    assert sha(canonical)==protocol['canonical_sha256']
    assert sha(root/'prepared/full.parquet')==protocol['full_sha256']
    source=pd.read_parquet(canonical)
    full=pd.read_parquet(root/'prepared/full.parquet').sequence.to_numpy(dtype=str)
    assert len(source)==590104 and source.gene_id.nunique()==466
    assert len(full)==590703 and len(set(full))==590703
    assert list(full)==sorted(set(source.sequence_ref)|set(source.sequence_alt))
    pilot=json.loads((root/'full-pilot.json').read_text())
    assert pilot['status']=='passed' and pilot['protocol_sha256']==protocol_hash
    assert pilot['native_controls_sha256']==sha(root/'prepared/full-native-controls.npz')
    for key,value in pilot['controls'].items():
        if key.endswith('embedding_relative_l2'):assert value < .005
        if key.endswith('delta_relative_l2'):assert value < .02
    for values in pilot['per_pair_delta_relative_l2'].values():
        assert max(values) < .02
    completions=[json.loads(p.read_text()) for p in sorted(root.glob('FULL-COMPLETE-*.json'))]
    assert completions, 'No completed workers'
    workers=completions[0]['workers']
    assert len(completions)==workers
    assert sorted(c['rank'] for c in completions)==list(range(workers))
    for item in completions:
        assert item['workers']==workers and item['protocol_sha256']==protocol_hash
        assert item['model_revision']==protocol['checkpoint_revision']
        assert item['model_weights_sha256']==pilot['model_weights_sha256']
        assert item['precision']=='float32'
        assert item['script_sha256']==pilot['script_sha256']
        assert not item['autocast'] and not item['tf32']
        assert item['controls']['embedding_relative_l2'] < .005
        assert item['controls']['delta_relative_l2'] < .02
        assert max(item['controls']['per_pair_delta_relative_l2']) < .02
        assert item['native_controls_sha256']==pilot['native_controls_sha256']
    assert len({c['model_weights_sha256'] for c in completions})==1
    assert len({c['script_sha256'] for c in completions})==1
    matrix=np.empty((len(full),1024),dtype=np.float32)
    written=np.zeros(len(full),dtype=bool)
    shards=sorted((root/'full-shards').glob(f'part-{workers}-*.npz'))
    assert shards
    sources={}
    for path in shards:
        with np.load(path,allow_pickle=False) as part:
            indices=part['indices'];features=part['embeddings']
            assert str(part['protocol_sha256'])==protocol_hash
            assert str(part['script_sha256'])==pilot['script_sha256']
            assert indices.ndim==1 and np.issubdtype(indices.dtype,np.integer)
            assert len(indices)==len(set(indices.tolist()))
            assert np.all((indices>=0)&(indices<len(full)))
            assert not written[indices].any()
            assert features.dtype==np.float32 and features.shape==(len(indices),1024)
            assert np.isfinite(features).all()
            matrix[indices]=features
            written[indices]=True
        sources[str(path.relative_to(root))]=sha(path)
    assert written.all() and np.isfinite(matrix).all()
    archive=root/'cpu/inputs/opensplice_ceno_full.npz'
    temporary=archive.with_suffix('.tmp.npz')
    np.savez(temporary,sequences=full,embeddings=matrix)
    temporary.replace(archive)
    metadata=dict(model='CladeTeam/CENO-1B-1m',revision=protocol['checkpoint_revision'],
                  pooling='mean_non_special_tokens',embedding_dim=1024,projection=None,
                  n_sequences=len(full),input=str(canonical),input_sha256=sha(canonical),
                  archive_sha256=sha(archive),storage_dtype='float32',compute_dtype='float32',
                  feature_origin='All 590703 sequences freshly computed uniformly on LUMI; no historical CUDA embeddings mixed in',
                  protocol_sha256=protocol_hash,pilot_sha256=sha(root/'full-pilot.json'),
                  worker_metadata=completions,shards_sha256=sources,finalizer_sha256=sha(Path(__file__)))
    write_json(archive.with_suffix('.json'),metadata)
    print('Merged uniform FP32 archive:',len(full),'sequences',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--stage',choices=['all','merge','evaluate','audit'],default='all')
    args=parser.parse_args()
    if args.stage in ['all','merge']:merge(args.root)
    if args.stage in ['all','evaluate']:
        verify_archived_folds(args.root)
        with capture_lsqr(args.root/'cpu/results/primary-solver-telemetry.json'):
            evaluate(args.root)
    if args.stage in ['all','audit']:audit(args.root)
    if args.stage=='all':
        solver_sensitivity(args.root)
        build_summary(args.root)
