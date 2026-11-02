#!/usr/bin/env python3
"""Matched-gene GTEx metrics and exact paired whole-gene percentile bootstrap."""
import argparse, hashlib, json, os, time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr
from numba import njit
p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--workers',type=int,default=8);p.add_argument('--replicates',type=int,default=10000);a=p.parse_args();r=a.run;o=r/'evaluation';o.mkdir(exist_ok=True)
from gtex_metrics import wrank, corr_weighted, ordering, contrast, ranks_matrix, retrieval, validate

validate()
N=np.load(r/'prepared/native_predictions.npz');genes=N['gene_ids'];tissues=N['tissues'];Y=N['truth'];n,T=Y.shape
models={}  # Same fixed statistics; this run evaluates only the new Evo2 predictor.
for name in ['evo2_20b']:
 path=r/name/'predictions.npz'
 if path.exists() and (r/name/'complete.json').exists():
  z=np.load(path);assert np.array_equal(z['tissues'],tissues);lookup={g:i for i,g in enumerate(z['gene_ids'])};M=z['predictions'][[lookup[g] for g in genes]];assert np.isfinite(M).all();models[name]=M
assert list(models)==['evo2_20b'], 'Completed Evo2 ridge predictions are required'
assert (n,T)==(5782,51) and a.replicates==10000
pairpath=o/'pairs.npz'
if pairpath.exists():
 assert hashlib.sha256(pairpath.read_bytes()).hexdigest()=='cedfda3740844e59fe04d342704c0185ae3302f6a994a6d63a71f384a0ea9ba3'
 z=np.load(pairpath);assert np.array_equal(z['genes'],genes) and np.array_equal(z['tissues'],tissues);maximum=z['maximum'];random_pair=z['random']
else:
 raise FileNotFoundError('Use original bundled data/bootstrap/pairs.npz; do not regenerate partner choices')
countpath=o/'bootstrap_counts.npy'
if not countpath.exists():
 raise FileNotFoundError('Use original bundled data/bootstrap/bootstrap_counts.npy; do not regenerate resamples')
counts=np.load(countpath,mmap_mode='r');assert counts.shape==(a.replicates,n) and np.all(counts.sum(1)==n)
COUNTS_DIGEST=hashlib.sha256(countpath.read_bytes()).hexdigest();assert COUNTS_DIGEST=='ed030943a78e7a5a8273fd6aa4883729b044be292f87c7cf90afb96f7ea81555';CODE_DIGEST=hashlib.sha256(Path(__file__).read_bytes()+(Path(__file__).parent/'gtex_metrics.py').read_bytes()).hexdigest()
CACHE={}
def setup(P,truth):
 return dict(pc=[ordering(contrast(P,pair)) for pair in [maximum,random_pair]],tc=[ordering(contrast(truth,pair)) for pair in [maximum,random_pair]],pr=[ordering(P[:,j]) for j in range(T)],tr=[ordering(truth[:,j]) for j in range(T)])
def one(C,w):
 values=[corr_weighted(wrank(*C['pc'][j],w,T),wrank(*C['tc'][j],w,T),w,T) for j in range(2)];P,pc=ranks_matrix(C['pr'],w);truth,tc=ranks_matrix(C['tr'],w);values.append(retrieval(P,truth));return values,pc+tc
def batch(args):
 name,lo,hi=args;C=CACHE[name];result=np.empty((hi-lo,3));invalid_profiles=np.zeros(hi-lo,np.int16)
 for b in range(lo,hi):result[b-lo],invalid_profiles[b-lo]=one(C,counts[b])
 return lo,hi,result,invalid_profiles
all_results=[];draws={};started=time.monotonic()
for name,P in models.items():
 truth=N['halfB'] if name=='split_half' else Y;C=setup(P,truth);CACHE[name]=C
 point,_=one(C,np.ones(n,dtype=np.uint16))
 # Full-data results independently verified against standard expanded-rank SciPy.
 for j,pair in enumerate([maximum,random_pair]):np.testing.assert_allclose(point[j],spearmanr(contrast(P,pair),contrast(truth,pair)).statistic,atol=1e-12,rtol=0)
 pr=rankdata(P,axis=0);tr=rankdata(truth,axis=0);pr-=pr.mean(0);tr-=tr.mean(0);np.testing.assert_allclose(point[2],retrieval(pr/np.linalg.norm(pr,axis=0),tr/np.linalg.norm(tr,axis=0)),atol=1e-12,rtol=0)
 # Independently verify an actual uint16-count bootstrap matrix against expanded rows.
 sample=np.repeat(np.arange(n),counts[0]);px=rankdata(P[sample],axis=0);tx=rankdata(truth[sample],axis=0);px-=px.mean(0);tx-=tx.mean(0);expected=(px/np.linalg.norm(px,axis=0)).T@(tx/np.linalg.norm(tx,axis=0));wp,_=ranks_matrix(C['pr'],counts[0]);wt,_=ranks_matrix(C['tr'],counts[0]);np.testing.assert_allclose(wp.T@wt,expected,atol=1e-12,rtol=0)
 fingerprint=hashlib.sha256(P.tobytes()+truth.tobytes()+maximum.tobytes()+random_pair.tobytes()+(COUNTS_DIGEST+CODE_DIGEST).encode()).hexdigest();path=o/f'{name}_bootstrap.npz';cached=None
 if path.exists():
  with np.load(path) as old:
   if str(old['fingerprint'])==fingerprint and old['draws'].shape==(a.replicates,3):cached=(old['draws'],old['constant_profiles'])
 if cached is not None:samples,invalid=cached
 else:
  samples=np.empty((a.replicates,3));invalid=np.zeros(a.replicates,np.int16)
  # Fork shares the frozen rank order arrays; only multiplicities change per draw.
  import multiprocessing as mp
  with ProcessPoolExecutor(max_workers=a.workers,mp_context=mp.get_context('fork')) as pool:
   for lo,hi,values,bad in pool.map(batch,[(name,i,min(i+100,a.replicates)) for i in range(0,a.replicates,100)]):
    samples[lo:hi]=values;invalid[lo:hi]=bad
    if hi%1000==0:print('BOOTSTRAP',name,hi,a.replicates,time.monotonic()-started,flush=True)
  np.savez(path,draws=samples,constant_profiles=invalid,fingerprint=fingerprint)
 draws[name]=samples
 for j,metric in enumerate(['maximum_contrast_spearman','random_contrast_spearman','retrieval_top1']):
  finite=np.isfinite(samples[:,j]);lo,hi=np.percentile(samples[finite,j],[2.5,97.5]);all_results.append(dict(model=name,metric=metric,value=point[j],low=lo,high=hi,n_genes=n,n_tissues=T,bootstrap_replicates=a.replicates,invalid_replicates=int((~finite).sum()),replicates_with_constant_profiles=int((invalid>0).sum())))
 pd.DataFrame(all_results).to_csv(o/'results.csv',index=False);print('SCORED',name,point,flush=True)
 CACHE.pop(name)
pairs=[]
for i,left in enumerate(models):
 for right in list(models)[i+1:]:
  for j,metric in enumerate(['maximum_contrast_spearman','random_contrast_spearman','retrieval_top1']):
   d=draws[left][:,j]-draws[right][:,j];finite=np.isfinite(d);lo,hi=np.percentile(d[finite],[2.5,97.5]);pointleft=next(x['value'] for x in all_results if x['model']==left and x['metric']==metric);pointright=next(x['value'] for x in all_results if x['model']==right and x['metric']==metric);pairs.append(dict(left=left,right=right,metric=metric,difference=pointleft-pointright,low=lo,high=hi,valid_replicates=int(finite.sum())))
pd.DataFrame(pairs).to_csv(o/'paired_differences.csv',index=False)
protocol=dict(models=list(models),required_models=['evo2_20b'],complete=len(models)==1,n_genes=n,n_tissues=T,bootstrap='paired whole-gene resampling, fixed51 candidates and queries, exact reranking through frequency-weighted ranks',seed=20260917,bootstrap_counts_sha256=COUNTS_DIGEST,rank_precision='float64, including square roots of integer multiplicities',replicates=a.replicates,confidence_interval='95% percentile',chance=dict(value=1/T,interval=None,style='plain gray bar'),maximum_pair_selection='from full observed log1p(TPM), same frozen partners for all models and split-half reference; lexicographic tissue tie break',reference='half A predicts half B on common genes and shared full-data contrast partners; uncertainty conditional on saved donor split',retrieval_ties='fractional credit among winners tied within absolute1e-12',random_pair_seed=20260918,invalid_handling='constant profiles make retrieval replicate invalid; report counts and omit invalid values from percentile, no silent denominator changes',validation='weighted-rank correlations checked against explicitly duplicated SciPy ranks; full point estimates cross-checked',script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),updated_unix=time.time())
(o/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n');print('EVALUATION COMPLETE',json.dumps(protocol),flush=True)
