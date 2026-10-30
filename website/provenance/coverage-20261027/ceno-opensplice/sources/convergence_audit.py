"""Independent numerical ridge solutions; original benchmark results stay intact."""
import argparse,json,time
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.linalg import cho_factor,cho_solve,eigvalsh
from scipy.stats import spearmanr
from sklearn.model_selection import GroupKFold
from genomic_bending.models.embeddings import load_embedding_archive,InterventionEmbeddingRidge
from readout_checks import capture_lsqr,verify_archived_folds
from finalize import sha,write_json

p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();R=a.root
out=R/'cpu/results/convergence';out.mkdir(exist_ok=True)
verify_archived_folds(R)
frame=pd.read_parquet(R/'cpu/inputs/canonical.parquet').reset_index(drop=True)
index,embeddings=load_embedding_archive(str(R/'cpu/inputs/opensplice_ceno_full.npz'))
primary_path=R/'cpu/results/opensplice_ceno_1b_1m_pretrained_gene_cv.predictions.parquet'
primary=pd.read_parquet(primary_path)
assert primary.record_id.to_list()==frame.record_id.to_list()
pred_chol=np.empty(len(frame),dtype=float);pred_lsqr=np.empty(len(frame),dtype=float)
reports=[];alpha=10.0
with capture_lsqr(out/'tight-lsqr-telemetry.json'):
    for fold,(train,test) in enumerate(GroupKFold(5).split(frame,groups=frame.gene_id.astype(str))):
        started=time.monotonic()
        model=InterventionEmbeddingRidge(index,embeddings,alpha=alpha)
        X=model._features(frame.iloc[train],fit=True)
        assert X.dtype==np.float64, X.dtype
        y=frame.iloc[train].delta_y.to_numpy(dtype=float)
        # Preserve the exact original sparse design, including float32 ALT-REF
        # subtraction before nuisance columns promote it to float64.
        dense=X.toarray(order='F')
        n,d=dense.shape
        mean=dense.mean(axis=0);mean_y=float(y.mean())
        gram=dense.T@dense-n*np.outer(mean,mean)
        rhs=dense.T@y-n*mean*mean_y
        gram.flat[::d+1]+=alpha
        factor=cho_factor(gram,lower=True,check_finite=True)
        beta=cho_solve(factor,rhs,check_finite=True)
        intercept=mean_y-mean@beta
        eigen=eigvalsh(gram,check_finite=True)
        assert eigen[0]>0 and np.isfinite(beta).all()
        def diagnostics(coef,bias):
            residual=dense@coef+bias-y
            gradient=dense.T@residual+alpha*coef
            # Intercept is fitted but not penalized.
            return dict(objective=float(residual@residual+alpha*(coef@coef)),
                        gradient_norm=float(np.linalg.norm(gradient)),
                        gradient_relative_to_rhs=float(np.linalg.norm(gradient)/(np.linalg.norm(rhs)+alpha*np.linalg.norm(coef))),
                        intercept_gradient=float(residual.sum()),
                        normal_equation_relative_backward_error=float(np.linalg.norm(gram@coef-rhs)/(np.linalg.norm(gram,2)*np.linalg.norm(coef)+np.linalg.norm(rhs))))
        chol_diag=diagnostics(beta,intercept)
        assert chol_diag['gradient_relative_to_rhs']<1e-9,chol_diag
        assert chol_diag['normal_equation_relative_backward_error']<1e-12,chol_diag
        print('CHOLESKY',fold+1,json.dumps(chol_diag),flush=True)
        model.regressor.tol=1e-10
        model.regressor.fit(X,y)
        lsqr_diag=diagnostics(model.regressor.coef_,float(model.regressor.intercept_))
        Xtest=model._features(frame.iloc[test],fit=False)
        c=Xtest@beta+intercept
        q=model.regressor.predict(Xtest)
        assert np.isfinite(c).all() and np.isfinite(q).all()
        pred_chol[test]=c;pred_lsqr[test]=q
        centered=c-c.mean()
        report=dict(fold=fold,training_rows=n,test_rows=len(test),features=d,source_design_dtype=str(X.dtype),
                    normal_equation_dtype=str(gram.dtype),ridge_alpha=alpha,lsqr_tolerance=1e-10,
                    regularized_eigenvalue_range=[float(eigen[0]),float(eigen[-1])],condition_number=float(eigen[-1]/eigen[0]),
                    cholesky=chol_diag,lsqr=lsqr_diag,lsqr_iterations=model.regressor.n_iter_.tolist(),
                    prediction_relative_l2=float(np.linalg.norm(c-q)/np.linalg.norm(centered)),
                    prediction_max_abs_difference=float(np.max(np.abs(c-q))),
                    coefficient_relative_l2=float(np.linalg.norm(beta-model.regressor.coef_)/np.linalg.norm(beta)),
                    seconds=time.monotonic()-started)
        reports.append(report);write_json(out/'fold-diagnostics.json',reports)
        print('CONVERGENCE_FOLD',json.dumps(report),flush=True)
        del X,Xtest,dense,gram,factor,model

predictions=primary[['record_id','gene_id','fold','y_true']].copy()
predictions['cholesky']=pred_chol;predictions['lsqr_1e10']=pred_lsqr
path=out/'predictions.parquet';predictions.to_parquet(path,index=False)
rows=[]
for gene,indices in frame.groupby('gene_id',sort=True).indices.items():
    truth=frame.iloc[indices].delta_y.to_numpy()
    rows.append(dict(gene_id=gene,n=len(indices),
                     primary=float(spearmanr(truth,primary.iloc[indices].y_pred).statistic),
                     cholesky=float(spearmanr(truth,pred_chol[indices]).statistic),
                     lsqr_1e10=float(spearmanr(truth,pred_lsqr[indices]).statistic)))
groups=pd.DataFrame(rows)
assert groups[['primary','cholesky','lsqr_1e10']].notna().all().all()
groups.to_csv(out/'per-gene.csv',index=False)
summary={}
for key in ['primary','cholesky','lsqr_1e10']:
    values=groups[key].to_numpy();rng=np.random.default_rng(20260822)
    ci=np.quantile(rng.choice(values,size=(2000,len(values)),replace=True).mean(axis=1),[.025,.975])
    summary[key]=dict(macro_spearman=float(values.mean()),ci95=ci.tolist())
differences=groups['cholesky'].to_numpy()-groups['primary'].to_numpy()
paired=np.random.default_rng(20260822).choice(differences,size=(2000,len(differences)),replace=True).mean(1)
report=dict(status='completed',primary_unchanged=True,protocol='Same features, alpha=10, intercept and archived folds; only numerical solver changed',
            records=590104,genes=466,summary=summary,cholesky_minus_primary=float(differences.mean()),
            difference_ci95=np.quantile(paired,[.025,.975]).tolist(),
            max_cholesky_lsqr_correlation_difference=float(np.max(np.abs(groups.cholesky-groups.lsqr_1e10))),
            max_fold_prediction_relative_l2=max(x['prediction_relative_l2'] for x in reports),
            all_cholesky_backward_errors_below_1e12=all(x['cholesky']['normal_equation_relative_backward_error']<1e-12 for x in reports),
            predictions_sha256=sha(path),primary_predictions_sha256=sha(primary_path),
            embedding_archive_sha256=sha(R/'cpu/inputs/opensplice_ceno_full.npz'),script_sha256=sha(Path(__file__)))
write_json(out/'RESULT.json',report)
print('CONVERGENCE_COMPLETE',json.dumps(report,indent=2),flush=True)
