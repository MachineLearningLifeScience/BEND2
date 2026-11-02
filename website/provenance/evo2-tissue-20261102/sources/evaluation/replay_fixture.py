#!/usr/bin/env python3
"""Developer portability test against an already accepted model; not Evo2 scoring.

The fixture must have been fitted in --work using the portable fit script under
its fixed evo2_20b key. Never report those fixture outputs as Evo2 results.
"""
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd
from gtex_metrics import contrast, ordering, wrank, corr_weighted, ranks_matrix, retrieval
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--work', type=Path, required=True)
p.add_argument('--reference', type=Path, required=True)
p.add_argument('--bootstrap', type=Path, required=True)
p.add_argument('--fixture-model', required=True)
a = p.parse_args()
r, c = a.work, a.reference
z = np.load(r/'evo2_20b/predictions.npz')
original = np.load(c/a.fixture_model/'predictions.npz')
error = float(np.max(np.abs(z['predictions']-original['predictions'])))
assert error < 1e-6
N = np.load(r/'prepared/native_predictions.npz')
lookup = {g:i for i,g in enumerate(original['gene_ids'])}
# Hold predictions fixed to isolate statistical-kernel portability from tiny BLAS differences.
P = original['predictions'][[lookup[g] for g in N['gene_ids']]]
Y=N['truth']; n,T=Y.shape
counts = np.load(a.bootstrap/'bootstrap_counts.npy', mmap_mode='r')
pairs = np.load(a.bootstrap/'pairs.npz')
pc=[ordering(contrast(P,pairs[k])) for k in ['maximum','random']]
tc=[ordering(contrast(Y,pairs[k])) for k in ['maximum','random']]
pr=[ordering(P[:,j]) for j in range(T)]
tr=[ordering(Y[:,j]) for j in range(T)]
def score(w):
    out=[corr_weighted(wrank(*pc[j],w,T),wrank(*tc[j],w,T),w,T) for j in range(2)]
    p,_=ranks_matrix(pr,w);t,_=ranks_matrix(tr,w)
    return np.array(out+[retrieval(p,t)])
point=score(np.ones(n,np.uint16))
summary=pd.read_csv(c/'evaluation/results.csv')
rows=summary[summary['model']==a.fixture_model]
np.testing.assert_allclose(point,rows.value.to_numpy(),atol=1e-12,rtol=0)
old=np.load(c/'evaluation'/f'{a.fixture_model}_bootstrap.npz')
indices=[0,137,9999]
draws=np.array([score(counts[i]) for i in indices])
np.testing.assert_allclose(draws,old['draws'][indices],atol=1e-12,rtol=0)
(r/'evaluation').mkdir(exist_ok=True)
for dst,src in [(r/'evaluation/bootstrap_counts.npy',a.bootstrap/'bootstrap_counts.npy'),
                (r/'evo2_20b/features.npy',c/a.fixture_model/'features.npy')]:
    if not dst.exists():dst.symlink_to(src)
# Diagnostic-only key alias lets the unmodified independent audit replay the new fit.
rows.assign(model='evo2_20b').to_csv(r/'evaluation/results.csv',index=False)
report=dict(status='passed',kind='portable CPU plumbing diagnostic, not an Evo2 result',
            fixture_model=a.fixture_model,full_prediction_max_abs_difference=error,
            all_three_point_metrics_match_for_fixed_predictions=True,
            bootstrap_draws_checked=indices,
            bootstrap_metric_max_abs_difference=float(np.max(np.abs(draws-old['draws'][indices]))),
            fixture_tissue_identification_percent=100*point[2])
(r/'PORTABILITY_TEST.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report),flush=True)
