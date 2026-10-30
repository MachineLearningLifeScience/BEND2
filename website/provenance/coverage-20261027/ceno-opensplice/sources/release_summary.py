"""Write a compact primary-result record after all independent audits finish."""
from pathlib import Path
import json,os
from finalize import sha, write_json


def build_summary(root):
    result_dir=root/'cpu/results'
    main=result_dir/'opensplice_ceno_1b_1m_pretrained_gene_cv.json'
    result=json.loads(main.read_text())
    audit=json.loads((result_dir/'AUDIT.json').read_text())
    fold=json.loads((result_dir/'ARCHIVED_FOLDS.json').read_text())
    sensitivity=json.loads((result_dir/'SOLVER_SENSITIVITY.json').read_text())
    pilot=json.loads((root/'full-pilot.json').read_text())
    archive=json.loads((root/'cpu/inputs/opensplice_ceno_full.json').read_text())
    telemetry=json.loads((result_dir/'primary-solver-telemetry.json').read_text())
    assert audit['status']==fold['status']==pilot['status']=='passed'
    assert result['n_records']==audit['n_records']==590104
    assert result['n_groups']==audit['n_genes']==466
    assert archive['n_sequences']==590703
    assert len(telemetry['calls'])==5
    files=[main,result_dir/'AUDIT.json',result_dir/'ARCHIVED_FOLDS.json',
           result_dir/'opensplice_ceno_1b_1m.per_gene.csv',result_dir/'SOLVER_SENSITIVITY.json',
           result_dir/'primary-solver-telemetry.json',result_dir/'strict-solver-telemetry.json',
           result_dir/'tolerance-sensitivity.per_gene.csv',root/'prepared/FULL_PROTOCOL.json',
           root/'full-pilot.json',root/'cpu/inputs/opensplice_ceno_full.json',
           root/'cpu/code/finalize.py',root/'cpu/code/finalize_full.py',root/'cpu/code/readout_checks.py',
           root/'cpu/code/release_summary.py',root/'code/extract_full.py']
    summary=dict(model='CENO-1B-1m',interface='embedding-fitted linear head',task='OpenSplice held-out genes',
                 metric='macro-gene Spearman',value=result['macro_spearman'],ci95=result['macro_spearman_ci95'],
                 higher_is_better=True,records=590104,genes=466,unique_sequences=590703,
                 correlation_eligible_genes=audit['n_correlation_eligible_genes'],
                 representation=dict(dimensions=1024,layer='final',pooling='mean_non_special_tokens',projection=None,
                                     precision='FP32',autocast=False,tf32=False,
                                     origin='All sequences freshly computed uniformly; historical CUDA cache excluded'),
                 readout=dict(target='raw delta_y',features=audit['features'],ridge_alpha=10,solver='lsqr',
                              intercept=True,normalization='none',primary_tolerance=sensitivity['primary_tolerance'],
                              folds='5 whole-gene GroupKFold; exact archived NTv3 assignments verified'),
                 bootstrap=audit['bootstrap'],canonical_sha256=audit['canonical_sha256'],
                 checkpoint_revision=pilot['model_revision'],weights_sha256=pilot['model_weights_sha256'],
                 model_code_sha256=pilot['model_code_sha256'],extraction_script_sha256=pilot['script_sha256'],
                 readout_source_sha256=audit['implementation_sha256'],
                 predictions_sha256=audit['predictions_sha256'],embedding_archive_sha256=audit['embedding_archive_sha256'],
                 passed_checks=['released native versus accelerated FP32 control','individual, permutation and padding controls',
                                'all-sequence finite coverage','archived fold-map identity','independent macro Spearman and bootstrap'],
                 primary_solver_stop_codes=[c['stop_code'] for c in telemetry['calls']],
                 primary_solver_iterations=[c['iterations'] for c in telemetry['calls']],
                 sensitivity=dict(separate_from_primary=True,strict_tolerance=sensitivity['strict_tolerance'],
                                  strict_macro_spearman=sensitivity['strict_macro_spearman'],
                                  strict_minus_primary=sensitivity['strict_minus_primary'],
                                  material_change=sensitivity['material_change']),
                 jobs=dict(gpu_production=(root/'production-job-id.txt').read_text().strip(),cpu=os.environ.get('SLURM_JOB_ID')),
                 environment=audit['environment'],
                 manifest={str(p.relative_to(root)):sha(p) for p in files})
    write_json(result_dir/'PRIMARY_RESULT.json',summary)
    print(json.dumps(summary,indent=2),flush=True)
