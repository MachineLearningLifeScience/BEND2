"""Describe the forced singleton query versus native BPE tokenization."""
import json, collections, hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from transformers import AutoTokenizer

R=Path('/scratch/project_465003339/ajeppese/bend-dnabert2-prior-20261027')
M=Path('/scratch/project_465003339/ajeppese/gimbench-gtex-extra-20260923/extra-models-direct/models--zhihan1996--DNABERT-2-117M/snapshots/b5d88cda421f106afef78cd286200a5b5b8f6fea')
tok=AutoTokenizer.from_pretrained(M,trust_remote_code=True,local_files_only=True)
table=pd.read_parquet(R/'windows.parquet').query('split == "evaluation"').reset_index(drop=True)
counts=collections.Counter();single=collections.Counter();centers=collections.Counter();center_single=collections.Counter();windows=0
for sequence in table.sequence:
    encoded=tok(sequence,add_special_tokens=False,return_offsets_mapping=True)
    tokens=tok.convert_ids_to_tokens(encoded['input_ids'])
    assert ''.join(tokens)==sequence
    hits=0
    for token,(start,end) in zip(tokens,encoded['offset_mapping']):
        counts[len(token)]+=1
        if len(token)==1:single[token]+=1
        if start<=600<end:
            centers[len(token)]+=1
            if len(token)==1:center_single[token]+=1
            hits+=1
    assert hits==1
    windows+=1
pred=pd.read_parquet(R/'predictions.parquet')
conf={a:{b:0 for b in 'ACGT'} for a in 'ACGT'}
for row in pred.itertuples():
    selected=max('ACGT',key=lambda b:getattr(row,'p_'+b))
    conf[row.true_base][selected]+=1
report=dict(n_windows=windows,total_native_tokens=sum(counts.values()),native_token_length_counts=dict(counts),
            native_singleton_counts=dict(single),native_singleton_fraction=sum(single.values())/sum(counts.values()),
            center_native_token_length_counts=dict(centers),center_native_singleton_counts=dict(center_single),
            mean_conditional_probabilities={b:float(pred['p_'+b].mean()) for b in 'ACGT'},
            conditional_query_confusion_true_rows=conf,
            script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
(R/'tokenization-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
