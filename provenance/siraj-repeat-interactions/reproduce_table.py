"""Extend the exact independent-repeat Figure 4 protocol to every Table 1 row.
CPU-only; original frozen predictions; no model/readout fitting or selection.
"""
import os
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:
    os.environ[key]='2'
from pathlib import Path
import itertools, json, hashlib, argparse
import numpy as np
import pandas as pd
from scipy.stats import rankdata
ap=argparse.ArgumentParser()
ap.add_argument('--archive',type=Path,required=True,help='Frozen repeat/prediction archive root')
ap.add_argument('--alphagenome-archive',type=Path,required=True,help='Frozen AlphaGenome table-completion archive root')
ap.add_argument('--input-dir',type=Path,default=Path(__file__).resolve().parent/'input')
ap.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parent)
args=ap.parse_args()
P=args.output_dir.resolve();P.mkdir(parents=True,exist_ok=True)
INPUT=args.input_dir.resolve();A=args.archive.resolve();M=args.alphagenome_archive.resolve()
def public_path(path):
    for base,label in [(INPUT,'input'),(A,'archive'),(M,'alphagenome-archive'),(P,'output')]:
        try:return label+'/'+str(path.resolve().relative_to(base))
        except ValueError:pass
    return path.name
KEY=['unit_id','mutation_position','mutation_ref','mutation_alt']
sources={}
def read(path,columns=None):
    with path.open('rb') as f: sources[public_path(path)]=hashlib.file_digest(f,'sha256').hexdigest()
    return pd.read_parquet(path,columns=columns)
raw=read(A/'iteration7/siraj-sign-epistasis/evaluation-input.parquet')
expected_hash=json.loads((INPUT/'fig4-VALIDATION.json').read_text())['source_files']['repeat-input/evaluation-input.parquet']
assert sources[public_path(A/'iteration7/siraj-sign-epistasis/evaluation-input.parquet')]==expected_hash
cell={c:raw[raw.context_id.eq(c)].set_index(KEY).sort_index() for c in ['HepG2','K562']}
keys=cell['HepG2'].index
assert keys.equals(cell['K562'].index) and len(keys)==68026
unit=keys.get_level_values('unit_id').to_numpy();units=sorted(set(unit));assert len(units)==114
pred={};lineage={};canonical=None
for name in ['ceno_1b_1m','dnabert2','ntv3_100m_pre','ntv3_100m_post','ntv3_650m_pre','ntv3_650m_post']:
    path=INPUT/(name+'.parquet');d=read(path).set_index(KEY,verify_integrity=True).loc[keys]
    assert len(d)==68026
    if canonical is None: canonical=d.y_true.to_numpy()
    else: np.testing.assert_allclose(d.y_true,canonical,atol=1e-12,rtol=0)
    pred[name]=d.y_pred.to_numpy()
    lineage[name]={'kind':'original saved paired predictions','path':public_path(path)}
# These native scores are exactly the cached cell-specific predictions already
# verified against the original Figure 4 sources in the previous analysis.
for name,column in [('alphagenome','AlphaGenome'),('enformer','Enformer')]:
    pred[name]=np.mean([(cell[c][column+'_A']-cell[c][column+'_R']).to_numpy() for c in cell],axis=0)
    lineage[name]={'kind':'original native predictions in verified repeat-input panel','path':public_path(A/'iteration7/siraj-sign-epistasis/evaluation-input.parquet')}
p=read(A/'reliability/siraj-direct_m0-mean-panel.parquet',columns=['ID','GENERATORv2_mean']).set_index('ID',verify_integrity=True).GENERATORv2_mean
pred['generator_v2_3b']=p.loc[cell['HepG2'].ID_A].to_numpy()-p.loc[cell['HepG2'].ID_R].to_numpy()
lineage['generator_v2_3b']={'kind':'original frozen mean-effect predictions','path':public_path(A/'reliability/siraj-direct_m0-mean-panel.parquet')}
path=M/'matched/results/siraj_background_interaction.predictions.parquet'
d=read(path).set_index(KEY,verify_integrity=True).loc[keys]
np.testing.assert_allclose(d.y_true,canonical,atol=1e-12,rtol=0)
pred['alphagenome_fitted']=d.y_pred.to_numpy()
lineage['alphagenome_fitted']={'kind':'matched-assay embedding-fitted original held-element-out head','path':public_path(path)}
for size in ['100m','650m']:
    name='ntv3_'+size+'_native';path=M/'table_completion/native-input'/f'{size}-scores.parquet'
    d=read(path,columns=['record_id','dnase_501_HepG2_log','dnase_501_K562_log']).set_index('record_id',verify_integrity=True)
    p=d.mean(axis=1)
    pred[name]=p.loc[cell['HepG2'].ID_A].to_numpy()-p.loc[cell['HepG2'].ID_R].to_numpy()
    lineage[name]={'kind':'native 501bp DNase log-coverage effects, averaged across cells','path':public_path(path)}
for name,v in pred.items():assert np.isfinite(v).all(),name
# Identical raw-repeat activity and pool construction as November 11 Figure 4.
I=[]
for rep in range(1,6):
    values=[]
    for c,d in cell.items():
        z={g:np.log2((d[f'{g}_rna{rep}'].to_numpy()+.5)/(d[f'{g}_dna{rep}'].to_numpy()+.5)) for g in ['R','R0','A','A0']}
        values.append(z['A']-z['A0']-z['R']+z['R0'])
    I.append(np.mean(values,axis=0))
I=np.array(I);pools=[]
for s in itertools.combinations(range(5),2):
    t=tuple(i for i in range(5) if i not in s)
    pools.extend([I[list(s)].mean(0),I[list(t)].mean(0)])
pools=np.array(pools)
def cr(x):
    if len(x)<2 or not np.isfinite(x).all():return np.full(len(x),np.nan)
    z=rankdata(x)-(len(x)+1)/2;norm=np.linalg.norm(z)
    return z/norm if norm else np.full(len(x),np.nan)
rows=[]
for locus in units:
    ix=np.flatnonzero(unit==locus);r=np.array([cr(v[ix]) for v in pools]);truth=cr(canonical[ix])
    rows.append(dict(model='experimental_reference',unit_id=locus,value=np.mean([np.dot(r[2*j],r[2*j+1]) for j in range(10)]),canonical=np.nan,edits=len(ix)))
    for name,v in pred.items():
        rank=cr(v[ix]);rows.append(dict(model=name,unit_id=locus,value=np.mean(r@rank),canonical=np.dot(truth,rank),edits=len(ix)))
per=pd.DataFrame(rows);per.to_csv(P/'per-locus.csv',index=False)
old=pd.read_csv(INPUT/'previous-table.csv').set_index('model')
bootix=np.random.default_rng(20261111).integers(114,size=(20000,114))
summary=[];checks={}
for name,g in per.groupby('model'):
    g=g.set_index('unit_id').loc[units];v=g.value.to_numpy();assert np.isfinite(v).all()
    bs=v[bootix].mean(1);lo,hi=np.quantile(bs,[.025,.975])
    previous=float(old.loc[name,'value'])
    cv=float(g.canonical.mean())
    if name!='experimental_reference':
        checks[name]=abs(cv-previous)
        assert checks[name]<1e-9,(name,cv,previous,checks[name])
    interface='Independent experimental repeat agreement' if name=='experimental_reference' else old.loc[name,'interface']
    summary.append(dict(model=name,value=float(v.mean()),ci_low=float(lo),ci_high=float(hi),loci=114,defined_loci=114,edits=68026,old_value=previous,canonical_replay=cv,computed_this_run=True,interface=interface))
new=pd.DataFrame(summary)
prior=pd.read_csv(INPUT/'fig4-summary.csv')
figchecks={}
for name in set(prior.model)&set(new.model):
    row=prior.set_index('model').loc[name];n=new.set_index('model').loc[name]
    err=max(abs(n.value-row.value),abs(n.ci_low-row.low),abs(n.ci_high-row.high))
    figchecks[name]=float(err);assert err<1e-12,(name,err)
# The previous fully validated run already used this exact protocol for these
# controls. Retain its estimates and intervals without rerunning GPU inference
# or replacing their original heads. Its original-label replay is in the receipt.
validation=json.loads((INPUT/'fig4-VALIDATION.json').read_text())
for name in ['evo2_20b','kmer_3_6','onehot_resnet','ntv3_650m_random']:
    r=prior.set_index('model').loc[name]
    original=float(old.loc[name,'value']) if name in old.index else np.nan
    can=pd.read_csv(INPUT/'fig4-canonical-summary.csv');can=can[(can.model==name)&(can.distance_bin=='all')].iloc[0]
    if np.isfinite(original):assert abs(original-can.value)<1e-9
    lineage[name]={'kind':'unchanged exact-protocol result from 20261111 verified run','path':public_path(INPUT/'fig4-summary.csv'),'original_source_paths':[p for p in validation['source_files'] if name.split('_')[0] in p]}
    summary.append(dict(model=name,value=float(r.value),ci_low=float(r.low),ci_high=float(r.high),loci=int(r.loci),defined_loci=int(r.defined_loci),edits=int(r.edits),old_value=original,canonical_replay=float(can.value),computed_this_run=False,interface=old.loc[name,'interface'] if name in old.index else 'matched random network'))
full=pd.DataFrame(summary)
need=set(old[old.value.notna()].index);assert need==set(full.model)-{'ntv3_650m_random'}
assert (full.loci==114).all() and (full.edits==68026).all()
full['metric']='macro-element Spearman';full['bootstrap_draws']=20000;full['bootstrap_seed']=20261111
full['reference_protocol']='all ten disjoint 2-vs-3 repeat partitions; mean across HepG2 and K562'
full.to_csv(P/'summary.csv',index=False)
full[full.model.isin(need)].to_csv(P/'table-ready.csv',index=False)
(P/'VALIDATION.json').write_text(json.dumps(dict(status='PASS',n_table_rows=len(need),n_models=len(need)-1,all_rows_same_114_loci_and_68026_edits=True,canonical_replay_errors=checks,previous_fig4_replay_errors=figchecks,previous_fig4_receipt=validation,bootstrap={'unit':'whole locus','draws':20000,'seed':20261111},source_files=sources,lineage=lineage,no_fitting=True,protocol='Same exact evaluation as Figure4 independent repeat protocol; existing fitted heads retain original published pooled-assay training labels.'),indent=2)+'\n')
print(full[['model','old_value','value','ci_low','ci_high','computed_this_run']].to_string(index=False));print('PASS',flush=True)
