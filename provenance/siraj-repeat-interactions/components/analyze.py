"""Matched single/double/interaction Siraj endpoints on all and strong edits."""
import os
for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:
    os.environ[k]='2'
from pathlib import Path
import argparse, hashlib, json
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ap=argparse.ArgumentParser()
ap.add_argument('--archive',type=Path,required=True)
ap.add_argument('--previous',type=Path,required=True)
ap.add_argument('--output',type=Path,required=True)
a=ap.parse_args(); a.output.mkdir(parents=True,exist_ok=True)
KEY=['unit_id','mutation_position','mutation_ref','mutation_alt']
sources={}
def public_path(path):
    for base,label in [(a.archive,'archive'),(a.previous,'strong-selection'),(a.output,'output')]:
        try:return label+'/'+str(path.resolve().relative_to(base.resolve()))
        except ValueError:pass
    return path.name
def read(path,columns=None):
    sources[public_path(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    return pd.read_parquet(path,columns=columns)
def centered(values, units):
    frame=pd.DataFrame(values)
    return (frame-frame.groupby(np.asarray(units)).transform('mean')).to_numpy()
def rho(x,y):
    if np.ptp(x)==0 or np.ptp(y)==0:return 0.
    return float(spearmanr(x,y).statistic)

old=read(a.previous/'analysis_input.parquet')
membership=read(a.previous/'memberships.parquet')
assert not old.duplicated(KEY).any()
old=old.set_index(KEY).sort_index()
membership=membership.set_index(KEY).loc[old.index]
keys=old.index
units=keys.get_level_values('unit_id').to_numpy()
all_units=sorted(np.unique(units));assert len(all_units)==114
chosen=membership['strong_0.5_depth0'].to_numpy(bool)
nchosen=pd.Series(chosen.astype(int),index=keys).groupby(level='unit_id').sum()
eligible=sorted(nchosen[nchosen>=20].index)
assert len(eligible)==89
all_mask=np.isin(units,eligible)
strong_mask=chosen&all_mask
assert all_mask.sum()==53101 and strong_mask.sum()==6136

raw=read(a.archive/'iteration7/siraj-sign-epistasis/evaluation-input.parquet')
assert not raw.duplicated(KEY+['context_id']).any()
assert len(raw)==136052
for rep in [4,5]:
    for state in ['R','A']:
        raw[f'e{state}{rep}']=np.log2((raw[f'{state}_rna{rep}']+.5)/(raw[f'{state}_dna{rep}']+.5))-np.log2((raw[f'{state}0_rna{rep}']+.5)/(raw[f'{state}0_dna{rep}']+.5))
        np.testing.assert_allclose(raw[f'e{state}{rep}'],raw[f'effect_{state}_rep{rep}'],rtol=0,atol=1e-12)
    raw[f'S{rep}']=(raw[f'eR{rep}']+raw[f'eA{rep}'])/2
    raw[f'R{rep}']=raw[f'eR{rep}']
    raw[f'D{rep}']=np.log2((raw[f'A_rna{rep}']+.5)/(raw[f'A_dna{rep}']+.5))-np.log2((raw[f'R0_rna{rep}']+.5)/(raw[f'R0_dna{rep}']+.5))
    raw[f'I{rep}']=raw[f'eA{rep}']-raw[f'eR{rep}']
for m in ['AlphaGenome','Enformer']:
    raw[f'{m}_S']=(raw[f'{m}_A']+raw[f'{m}_R'])/2
    raw[f'{m}_I']=raw[f'{m}_A']-raw[f'{m}_R']
cols=['AlphaGenome_R','AlphaGenome_A','Enformer_R','Enformer_A','R4','R5','D4','D5','eA4','eA5','S4','S5','I4','I5','AlphaGenome_S','AlphaGenome_I','Enformer_S','Enformer_I']
frame=raw.groupby(KEY)[cols].mean().loc[keys]
assert np.isfinite(frame.to_numpy()).all()
np.testing.assert_allclose(centered(frame[['I4','I5']].to_numpy(),units),old[['I4','I5']].to_numpy(),rtol=0,atol=1e-12)

pred={
    'AlphaGenome native':{'R':frame.AlphaGenome_R.to_numpy(),'D':frame.AlphaGenome_A.to_numpy(),'S':frame.AlphaGenome_S.to_numpy(),'I':frame.AlphaGenome_I.to_numpy()},
    'Enformer native':{'R':frame.Enformer_R.to_numpy(),'D':frame.Enformer_A.to_numpy(),'S':frame.Enformer_S.to_numpy(),'I':frame.Enformer_I.to_numpy()},
}
def background_parts(data,column):
    data=data.copy()
    data=data.merge(keys.to_frame(index=False),on=KEY,how='inner',validate='many_to_one')
    data['state']=data.background_id.str.extract(r':([AR]):w')[0]
    assert not data.duplicated(KEY+['state']).any()
    wide=data.pivot(index=KEY,columns='state',values=column).reindex(keys)
    assert np.isfinite(wide[['A','R']].to_numpy()).all()
    return {'R':wide.R.to_numpy(),'D':wide.A.to_numpy(),'S':((wide.A+wide.R)/2).to_numpy(),'I':(wide.A-wide.R).to_numpy()}
for state in ['pre','post']:
    path=a.archive/f'iteration2/reliability/plain_mlp/nt650_{state}/oof_predictions.parquet'
    d=read(path,columns=KEY+['background_id','ridge_raw10_mean'])
    pred[f'NTv3 650M {state} linear']=background_parts(d,'ridge_raw10_mean')
id_path=a.archive/'reliability/siraj-direct_m0-cohort.csv'
sources[public_path(id_path)]=hashlib.sha256(id_path.read_bytes()).hexdigest()
ids=pd.read_csv(id_path,usecols=['ID','background_id']+KEY)
extra=read(a.archive/'reliability/siraj-direct_m0-mean-panel.parquet',columns=['ID','NTv3_100M_post_mean','GENERATORv2_mean'])
extra=extra.merge(ids,on='ID',validate='one_to_one')
for m,col in [('NTv3 100M post linear','NTv3_100M_post_mean'),('GENERATORv2 linear','GENERATORv2_mean')]:
    pred[m]=background_parts(extra,col)
oldcols={'AlphaGenome native':'AlphaGenome','Enformer native':'Enformer',
         'NTv3 650M pre linear':'nt_pre','NTv3 650M post linear':'nt_post',
         'NTv3 100M post linear':'NTv3_100M_post_background','GENERATORv2 linear':'GENERATORv2_background'}
reconstruction={}
for m,values in pred.items():
    reconstructed=centered(values['I'][:,None],units)[:,0]
    expected=old[oldcols[m]].to_numpy()
    reconstruction[m]=float(np.max(np.abs(reconstructed-expected)))
    np.testing.assert_allclose(reconstructed,expected,rtol=0,atol=1e-10,err_msg=m)
    # Use the identical frozen interaction array after verifying its lineage.
    values['I']=expected

for values in pred.values():
    np.testing.assert_allclose(centered(values['R'][:,None],units),centered((values['S']-values['I']/2)[:,None],units),atol=1e-10)
    np.testing.assert_allclose(centered(values['D'][:,None],units),centered((values['S']+values['I']/2)[:,None],units),atol=1e-10)
# Within a locus, adding the fixed background-SNP effect leaves ranks unchanged.
for unit in eligible:
    ix=units==unit
    for rep in [4,5]:
        d=(frame[f'D{rep}']-frame[f'eA{rep}']).to_numpy()[ix]
        assert np.ptp(d)<1e-12
contexts=sorted(raw.context_id.unique());assert len(contexts)==2
assert {str(c).lower() for c in contexts}=={'hepg2','k562'}
by_cell={c:raw[raw.context_id==c].set_index(KEY).loc[keys] for c in contexts}
assert all(len(v)==len(keys) for v in by_cell.values())
rows=[]
for cohort,mask,endpoints in [('all_edits',all_mask,['single_effect','combined_effect','interaction']),('strong',strong_mask,['single_effect','combined_effect','interaction'])]:
    for unit in eligible:
        idx=np.flatnonzero(mask&(units==unit))
        assert len(idx)>=20
        for endpoint in endpoints:
            col={'single_effect':'R','combined_effect':'D','interaction':'I'}[endpoint]
            a4=frame[f'{col}4'].to_numpy()[idx];a5=frame[f'{col}5'].to_numpy()[idx]
            ref=rho(a4,a5)
            transfer=np.mean([rho(by_cell[contexts[0]][f'{col}{rep}'].to_numpy()[idx],by_cell[contexts[1]][f'{col}{rep}'].to_numpy()[idx]) for rep in [4,5]])
            for m,values in pred.items():
                p=values[col][idx]
                rows.append(dict(cohort=cohort,endpoint=endpoint,model=m,unit_id=unit,n=len(idx),
                                 model_spearman=(rho(p,a4)+rho(p,a5))/2,repeat_spearman=ref,cross_cell_spearman=transfer))
per=pd.DataFrame(rows)
per.to_csv(a.output/'per_locus.csv',index=False)
counts=np.random.default_rng(20261110).multinomial(114,np.full(114,1/114),size=20000).astype(float)
weights=counts[:,[all_units.index(u) for u in eligible]]
weights/=weights.sum(axis=1,keepdims=True)
summary=[]
for (cohort,endpoint,m),g in per.groupby(['cohort','endpoint','model']):
    g=g.set_index('unit_id').loc[eligible]
    for metric in ['model_spearman','repeat_spearman','cross_cell_spearman']:
        v=g[metric].to_numpy();lo,hi=np.quantile(weights@v,[.025,.975])
        summary.append(dict(cohort=cohort,endpoint=endpoint,model=m,metric=metric,
                            value=float(v.mean()),low=float(lo),high=float(hi),loci=len(g),edits=int(g.n.sum())))
summary=pd.DataFrame(summary)
prior=pd.read_csv(a.previous/'summary.csv')
replay_error=0.
for row in summary[summary.endpoint.eq('interaction')&summary.metric.isin(['model_spearman','repeat_spearman'])].itertuples():
    cohort='matched_all__strong_0.5_depth0' if row.cohort=='all_edits' else 'strong_0.5_depth0'
    target=prior[(prior.cohort==cohort)&(prior.model==row.model)&(prior.metric==row.metric)]
    assert len(target)==1
    actual=np.array([row.value,row.low,row.high]);expected=target[['value','low','high']].iloc[0].to_numpy(float)
    replay_error=max(replay_error,float(np.max(np.abs(actual-expected))))
    np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-12)
summary.to_csv(a.output/'summary.csv',index=False)
record=dict(sources=sources,loci=89,all_edits=53101,strong_edits=6136,evaluation_replicates=[4,5],
            fitted_predictions='Existing heads only; no fitting or calibration in this analysis',
            interaction_reconstruction_max_error=reconstruction,interaction_summary_replay_max_error=replay_error,
            bootstrap=dict(draws=20000,seed=20261110,unit='whole locus',sampling='114-locus multinomial multiplicities renormalized over fixed89 eligible loci'),
            cross_cell_reference='Mean of within-locus HepG2 versus K562 Spearman, calculated separately in evaluation replicates4 and5',
            repeat_reference='Within-locus Spearman between cell-averaged outcomes in evaluation repeats4 and5',
            missing_handling='Require finite aligned inputs, constant vectors contribute zero correlation as in frozen strong-subset protocol',
            single_definition='Query effect on reference background R',
            double_definition='Background SNP plus query relative to reference parent; parent offset constant within locus so ranks equal query effect on A',
            interaction_definition='Query effect on A minus query effect on R; full-locus centering does not alter within-subset correlations',
            membership='Frozen strong_0.5_depth0 mask from discovery replicates1–3; no reselection')
(a.output/'VALIDATION.json').write_text(json.dumps(record,indent=2)+'\n')
print(summary[(summary.metric=='model_spearman')][['cohort','endpoint','model','value','low','high']].to_string(index=False))
print('EXPERIMENTAL',summary[(summary.metric.isin(['repeat_spearman','cross_cell_spearman'])) & (summary.model=='AlphaGenome native')][['cohort','endpoint','metric','value','low','high']].to_string(index=False))
print('PASS frozen interaction replay',replay_error,flush=True)
