"""Audit fold identities and solver precision without replacing primary results."""
from contextlib import contextmanager
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge
from sklearn.linear_model import _ridge
from sklearn.model_selection import GroupKFold
from genomic_bending.models.embeddings import load_embedding_archive, InterventionEmbeddingRidge
from finalize import sha, write_json


@contextmanager
def capture_lsqr(path):
    original=_ridge.sp_linalg.lsqr
    events=[]
    def observed(*args,**kwargs):
        result=original(*args,**kwargs)
        events.append(dict(shape=list(args[0].shape),atol=kwargs.get('atol'),btol=kwargs.get('btol'),
                           iter_lim=kwargs.get('iter_lim'),stop_code=int(result[1]),iterations=int(result[2]),
                           residual_norm=float(result[3]),regularized_residual_norm=float(result[4]),
                           operator_norm=float(result[5]),condition_estimate=float(result[6]),
                           normal_equation_residual_norm=float(result[7]),solution_norm=float(result[8])))
        write_json(path,dict(note='Transparent observer; original LSQR arguments and return value unchanged',calls=events))
        return result
    _ridge.sp_linalg.lsqr=observed
    try:yield
    finally:_ridge.sp_linalg.lsqr=original


def verify_archived_folds(root):
    cpu=root/'cpu'
    reference=cpu/'inputs/archived-ntv3-650m-post-folds.parquet'
    ref=pd.read_parquet(reference)
    frame=pd.read_parquet(cpu/'inputs/canonical.parquet')
    assert len(ref)==len(frame)==590104
    assert ref.record_id.is_unique
    merged=frame[['record_id','gene_id']].merge(ref,on=['record_id','gene_id'],how='left',validate='one_to_one',sort=False)
    assert merged.fold.notna().all()
    assert merged.record_id.to_list()==frame.record_id.to_list()
    regenerated=np.full(len(frame),-1,dtype=int)
    for fold,(_,test) in enumerate(GroupKFold(5).split(frame,groups=frame.gene_id.astype(str))):
        regenerated[test]=fold
    assert np.array_equal(regenerated,merged.fold.to_numpy())
    report=dict(status='passed',records=len(frame),genes=frame.gene_id.nunique(),
                archived_foldmap_sha256=sha(reference),canonical_sha256=sha(cpu/'inputs/canonical.parquet'),
                original_provenance=json.loads(reference.with_suffix('.json').read_text()),
                fold_rows=np.bincount(regenerated).tolist())
    write_json(cpu/'results/ARCHIVED_FOLDS.json',report)
    print('Archived NTv3 fold map matches all 590104 records',flush=True)


def solver_sensitivity(root):
    cpu=root/'cpu'
    canonical=cpu/'inputs/canonical.parquet'
    frame=pd.read_parquet(canonical).reset_index(drop=True)
    primary_path=cpu/'results/opensplice_ceno_1b_1m_pretrained_gene_cv.predictions.parquet'
    primary=pd.read_parquet(primary_path)
    assert primary.record_id.to_list()==frame.record_id.to_list()
    index,embeddings=load_embedding_archive(str(cpu/'inputs/opensplice_ceno_full.npz'))
    default_tol=Ridge(alpha=10,solver='lsqr').tol
    strict_tol=default_tol/100
    prediction=np.empty(len(frame),dtype=float)
    with capture_lsqr(cpu/'results/strict-solver-telemetry.json'):
        for fold,(train,test) in enumerate(GroupKFold(5).split(frame,groups=frame.gene_id.astype(str))):
            model=InterventionEmbeddingRidge(index,embeddings,alpha=10)
            model.regressor.tol=strict_tol
            model.fit(frame.iloc[train],target='delta_y')
            prediction[test]=model.predict(frame.iloc[test])
            print('Strict-tolerance sensitivity fold',fold+1,'/5',flush=True)
    assert np.isfinite(prediction).all()
    output=primary[['record_id','gene_id','fold','y_true']].copy()
    output['y_pred']=prediction
    strict_path=cpu/'results/opensplice_ceno_strict_tolerance.predictions.parquet'
    output.to_parquet(strict_path,index=False)
    rows=[]
    for gene,indices in frame.groupby('gene_id',sort=True).indices.items():
        truth=frame.iloc[indices].delta_y.to_numpy()
        rows.append(dict(gene_id=gene,primary=float(spearmanr(truth,primary.iloc[indices].y_pred).statistic),
                         strict=float(spearmanr(truth,prediction[indices]).statistic)))
    groups=pd.DataFrame(rows).dropna()
    difference=groups['strict'].to_numpy()-groups['primary'].to_numpy()
    rng=np.random.default_rng(20260822)
    draws=rng.choice(difference,size=(2000,len(difference)),replace=True).mean(axis=1)
    groups.to_csv(cpu/'results/tolerance-sensitivity.per_gene.csv',index=False)
    result=dict(primary_result_preserved=True,primary_tolerance=default_tol,strict_tolerance=strict_tol,
                primary_macro_spearman=float(groups['primary'].mean()),strict_macro_spearman=float(groups['strict'].mean()),
                strict_minus_primary=float(difference.mean()),difference_ci95=np.quantile(draws,[.025,.975]).tolist(),
                prediction_difference_rms=float(np.sqrt(np.mean((prediction-primary.y_pred.to_numpy())**2))),
                prediction_difference_max=float(np.max(np.abs(prediction-primary.y_pred.to_numpy()))),
                material_change_threshold=.001,material_change=bool(abs(difference.mean())>.001),
                primary_predictions_sha256=sha(primary_path),strict_predictions_sha256=sha(strict_path),
                script_sha256=sha(Path(__file__)),
                note='Sensitivity check only. Primary uses the unmodified CLI default tolerance; no result is selected or substituted based on this check.')
    write_json(cpu/'results/SOLVER_SENSITIVITY.json',result)
    print(json.dumps(result,indent=2),flush=True)
