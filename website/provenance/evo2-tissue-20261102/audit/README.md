# Evo2 return check — 2 November 2026

The new return passes the numerical and extraction audits and is suitable for
filling the missing Evo2 20B tissue-identification result. It uses native FP8
with a documented two-H100 block-sharding adaptation. All 4,489 previously
completed feature rows are exactly preserved, and the remaining 14,793 are
complete. See `extraction-review.md` for the model-use and continuation checks.

| Evaluation | Score | 95% interval |
|---|---:|---:|
| Tissue identification | 21.5686% | 7.8431–21.5686% |
| Maximum tissue-contrast Spearman | 0.605121 | 0.593382–0.616722 |
| Random tissue-contrast Spearman | 0.468919 | 0.460332–0.477364 |

Tissue identification correctly matches 11 of 51 tissue profiles, using
5,782 held-out genes. A predicted tissue's profile is correlated against
all 51 measured tissue profiles, and the best match is selected. This is
not per-gene tissue classification. Random identification is 1/51 (1.9608%).
The readout fits 51 tissue outputs from 512-dimensional frozen Evo2 features.

## Independent checks

- Archive CRC and all 25 manifest entries (size and SHA256) pass.
- All 19,282 embedding rows are present, finite and nonzero.
- Original data ordering, targets, train/validation indices and common test
  cohort match the frozen handoff.
- All seven evaluation-script hashes, including the finalizer, match the
  original handoff.
- Independent training-only standardization and ridge fitting select alpha=1.
  Predictions match with a maximum absolute error of 6.96e-10.
- All three point estimates reproduce with SciPy ranks.
- The reported intervals reproduce from all 10,000 returned bootstrap draws;
  33 independently expanded and reranked draws match for all three metrics.

The intervals resample whole held-out genes with fixed tissue queries and a
fixed fitted readout. They do not resample donors or refit the model. The tissue
identification interval is asymmetric and discrete; its upper bound equals the
point estimate after rounding. See `metric-review.md` for the distribution check.

## Comparison with the prior return

The rejected BF16 diagnostic gave 7.8431% tissue identification. This return
uses native FP8 and continues the original extraction protocol. Its tissue score
is 13.7255 percentage points higher. These are different inference configurations;
the BF16 diagnostic should not replace the standard result.

## Scope and provenance

This fills the previously missing Evo2 **tissue-identification** result; it also
supplies the two GTEx expression-contrast endpoints. It is not a new run of the
other benchmark tasks. The website, manuscript, remote repositories and GPU
jobs were not changed by this check.

GPU inference was not rerun locally. Runtime/model use was checked against
returned code, provenance, numerical controls and the original saved features.
The previously documented eight pseudoautosomal test windows identical to
training/validation windows are inherited from the shared cohort, rather than
introduced by this return; this audit does not alter that cohort.

Reproduce the CPU audit with:

```sh
uv run --with numpy --with scipy python audit_return.py
```

The audit script locates the original frozen handoff beside this audit folder.
No Python or pickle file from the returned archive was executed or deserialized.

Archive SHA256: `4572ece88daa9f448ca9b7d81a2182d5ca26e5b5287e6798aa38ef1c2cb8c253`.
