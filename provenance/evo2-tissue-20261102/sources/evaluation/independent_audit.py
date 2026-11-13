"""Independent completed-prediction replay and scikit-learn ridge verification."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np,pandas as pd
from scipy.stats import rankdata
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--models',nargs='+',default=['evo2_20b']);a=p.parse_args();r=a.run
D=np.load(r/'prepared/targets.npz');N=np.load(r/'prepared/native_predictions.npz');tr=D['train'];va=D['validation'];rows=[]
expected='ed030943a78e7a5a8273fd6aa4883729b044be292f87c7cf90afb96f7ea81555'
assert hashlib.sha256((r/'evaluation/bootstrap_counts.npy').read_bytes()).hexdigest()==expected
summary=pd.read_csv(r/'evaluation/results.csv')
truth=rankdata(N['truth'],axis=0);truth-=truth.mean(0);truth/=np.linalg.norm(truth,axis=0)
for model in a.models:
 o=r/model;z=np.load(o/'predictions.npz');protocol=json.loads((o/'protocol.json').read_text());X=np.load(o/'features.npy').astype(float);Y=D['truth'];assert z['predictions'].shape==Y.shape
 np.testing.assert_array_equal(z['gene_ids'],D['gene_ids']);np.testing.assert_array_equal(z['tissues'],D['tissues'])
 xs=StandardScaler().fit(X[tr]);ys=StandardScaler().fit(Y[tr]);Xt=xs.transform(X[tr]);Yt=ys.transform(Y[tr]);
 # Independently recompute the entire validation alpha choice, not only final weights.
 independent_scores=[];best=None
 for candidate in [10000.,1000.,100.,10.,1.,.1]:
  candidate_ridge=Ridge(alpha=candidate,solver='cholesky',fit_intercept=False).fit(Xt,Yt)
  mse=float(np.mean((candidate_ridge.predict(xs.transform(X[va]))-ys.transform(Y[va]))**2))
  independent_scores.append(dict(alpha=candidate,validation_standardized_mse=mse))
  if best is None or mse<best[0]-1e-12:best=(mse,candidate)
 assert best[1]==protocol['alpha'],(model,best,protocol['alpha'])
 ridge=Ridge(alpha=protocol['alpha'],solver='cholesky',fit_intercept=False).fit(Xt,Yt)
 independent=ys.inverse_transform(ridge.predict(xs.transform(X)));err=float(np.max(np.abs(independent-z['predictions'])));assert err<1e-6,(model,err)
 ids={g:i for i,g in enumerate(z['gene_ids'])};pred=z['predictions'][[ids[g] for g in N['gene_ids']]];pr=rankdata(pred,axis=0);pr-=pr.mean(0);pr/=np.linalg.norm(pr,axis=0);corr=pr.T@truth;wins=np.isclose(corr,corr.max(1)[:,None],atol=1e-12,rtol=0);score=float(np.mean(np.diag(wins)/wins.sum(1)))
 reported=summary.query('model==@model and metric=="retrieval_top1"').iloc[0];assert abs(score-reported.value)<1e-12
 assert not np.intersect1d(np.r_[tr,va],N['global_indices']).size
 pd.DataFrame(corr,index=N['tissues'],columns=N['tissues']).to_csv(o/'retrieval_confusion.csv')
 rows.append(dict(model=model,tissue_id_percent=100*score,ci95_percent=[100*reported.low,100*reported.high],ridge_alpha=protocol['alpha'],ridge_prediction_max_abs_error=err,independent_validation=independent_scores,n_train=len(tr),n_validation=len(va),n_test=len(pred),n_tissues=51,no_test_fit_overlap=True,predictions_sha256=hashlib.sha256((o/'predictions.npz').read_bytes()).hexdigest()))
(r/'independent-audit.json').write_text(json.dumps(dict(checks='independent SciPy rank retrieval plus sklearn Cholesky ridge replay; exact frozen paired bootstrap hash',bootstrap_counts_sha256=expected,results=rows),indent=2));print('INDEPENDENT AUDIT PASSED',json.dumps(rows),flush=True)
