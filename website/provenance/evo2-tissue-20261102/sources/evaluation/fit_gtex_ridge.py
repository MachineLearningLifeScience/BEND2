#!/usr/bin/env python3
"""Frozen Evo2 tissue readout with training-only scaling and validation alpha choice.

Invocation: python fit_gtex_ridge.py --run WORK --model evo2_20b
Normally invoked by finalize_evo2.py after its input and completeness checks.
"""
import argparse, hashlib, json, time
from pathlib import Path
import numpy as np
from numba import njit, prange, set_num_threads
from sklearn.preprocessing import StandardScaler
p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--model',choices=['kmer_3_6','evo2_20b'],required=True);a=p.parse_args();r=a.run;o=r/a.model;o.mkdir(exist_ok=True)
D=np.load(r/'prepared/targets.npz');tr=D['train'];va=D['validation'];Y=D['truth']
@njit(parallel=True,cache=True)
def count(sequences):
 out=np.zeros((len(sequences),5440),np.float32)
 for i in prange(len(sequences)):
  code=0;valid=0
  for b in sequences[i]:
   if b>3:code=0;valid=0;continue
   code=((code<<2)|int(b))&4095;valid+=1
   if valid>=3:out[i,code&63]+=1
   if valid>=4:out[i,64+(code&255)]+=1
   if valid>=5:out[i,320+(code&1023)]+=1
   if valid>=6:out[i,1344+code]+=1
 return out
if a.model=='kmer_3_6':
 seq=np.load(r/'prepared/sequences.npy',mmap_mode='r')
 set_num_threads(16)
 # Cross-check rolling counts against a direct enumerator including ambiguous bases.
 small=np.array([[0,1,2,3,4,0,0,0,1,2,3,1,2]],np.uint8);expected=np.zeros(5440)
 for k,offset in [(3,0),(4,64),(5,320),(6,1344)]:
  for j in range(small.shape[1]-k+1):
   window=small[0,j:j+k]
   if (window<4).all():expected[offset+sum(int(b)*4**(k-1-z) for z,b in enumerate(window))]+=1
 np.testing.assert_array_equal(count(small)[0],expected)
 path=o/'features.npy'
 if not path.exists():
  started=time.monotonic();X=count(seq);np.save(path,X);print('COUNTS COMPLETE',time.monotonic()-started,flush=True)
 X=np.load(path)
else:
 assert (r/'evo2/complete.json').exists(),'Evo2 extraction must be complete before fitting'
 X=np.load(r/'evo2/embeddings.npy').astype(np.float64)
assert len(X)==len(Y) and np.isfinite(X).all()
xs=StandardScaler().fit(X[tr]);ys=StandardScaler().fit(Y[tr]);Xt=xs.transform(X[tr]).astype(np.float64);Yt=ys.transform(Y[tr]);Xv=xs.transform(X[va]).astype(np.float64);Yv=ys.transform(Y[va])
# One eigendecomposition gives the exact ridge solution for every candidate alpha.
G=Xt.T@Xt;cross=Xt.T@Yt;print('GRAM READY',flush=True);eig,V=np.linalg.eigh(G);assert eig.min()>-1e-6;eig=np.maximum(eig,0);projected=V.T@cross
scores=[];best=None
for alpha in [10000.,1000.,100.,10.,1.,.1]:
 coef=V@(projected/(eig[:,None]+alpha));mse=float(np.mean((Xv@coef-Yv)**2));scores.append(dict(alpha=alpha,validation_standardized_mse=mse))
 if best is None or mse<best[0]-1e-12:best=(mse,alpha,coef)
 print('VALIDATION',scores[-1],flush=True)
_,alpha,coef=best;pred=ys.inverse_transform(xs.transform(X).astype(np.float64)@coef)
np.savez(o/'predictions.npz',gene_ids=D['gene_ids'],tissues=D['tissues'],predictions=pred)
np.savez(o/'fit.npz',coef=coef,feature_mean=xs.mean_,feature_scale=xs.scale_,target_mean=ys.mean_,target_scale=ys.scale_,alpha=alpha)
protocol=dict(model=a.model,alpha=alpha,alpha_grid=[.1,1,10,100,1000,10000],selection='validation standardized MSE, one shared alpha across51 tissue heads; ties choose stronger penalty',n_fit=len(tr),n_validation=len(va),feature_dim=X.shape[1],input='131072bp reference-forward TSS-centered sequence',target='51 separate coefficients/intercepts predicting log1p(TPM); target inverse-scaled before evaluation',preprocessing='StandardScaler fit on training genes only; final fit retains training-only membership',validation=scores,seed=20260917,prepared_protocol_sha256=hashlib.sha256((r/'prepared/protocol.json').read_bytes()).hexdigest(),script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
(o/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n');(o/'complete.json').write_text(json.dumps({'finished_unix':time.time(),'predictions_sha256':hashlib.sha256((o/'predictions.npz').read_bytes()).hexdigest()},indent=2)+'\n');print('RIDGE COMPLETE',a.model,alpha,flush=True)
