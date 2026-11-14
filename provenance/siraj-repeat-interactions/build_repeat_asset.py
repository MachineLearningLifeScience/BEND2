from pathlib import Path
import argparse,hashlib,json,numpy as np,pandas as pd
p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
key=['unit_id','mutation_position','mutation_ref','mutation_alt'];r=pd.read_parquet(a.input);c={s:r[r.context_id.eq(s)].set_index(key).sort_index() for s in ['HepG2','K562']};ix=c['HepG2'].index
assert ix.equals(c['K562'].index) and len(ix)==68026 and len(set(ix.get_level_values('unit_id')))==114
out=ix.to_frame(index=False)
for rep in range(1,6):
 v=[]
 for d in c.values():
  z={g:np.log2((d[f'{g}_rna{rep}'].to_numpy()+.5)/(d[f'{g}_dna{rep}'].to_numpy()+.5)) for g in ['R','R0','A','A0']}
  v.append(z['A']-z['A0']-z['R']+z['R0'])
 out[f'interaction_repeat_{rep}']=np.mean(v,axis=0)
a.output.parent.mkdir(parents=True,exist_ok=True);out.to_parquet(a.output,index=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
receipt=dict(source_sha256=sha(a.input),output_sha256=sha(a.output),bytes=a.output.stat().st_size,n_pairs=len(out),n_elements=114,columns=list(out),dtype='float64',formula='mean across HepG2 and K562 of log2((A_RNA+.5)/(A_DNA+.5)) - log2((A0_RNA+.5)/(A0_DNA+.5)) - log2((R_RNA+.5)/(R_DNA+.5)) + log2((R0_RNA+.5)/(R0_DNA+.5)), separately for each of five experimental repeats')
a.output.with_suffix('.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
