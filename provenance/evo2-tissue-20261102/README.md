# Evo2 20B tissue-identification evaluation

The accepted native-FP8 return fills the previously missing tissue-identification
cell with **21.568627450980394%**, displayed as **21.6%**: 11 correct matches among
51 tissue profiles over 5,782 held-out genes. Evaluation completed on 31 October
2026 and independent numerical and extraction reviews passed on 2 November.

The run continues the original pinned Evo2 20B extraction using 131,072-bp
reference-forward TSS windows, layer `blocks.20.mlp.l3`, the original pooling,
and SRHT projection to 512 features. All 19,282 rows are complete; the original
4,489 feature rows are exactly preserved. A documented two-H100 block-sharding
and Transformer Engine state adapter permits native-FP8 continuation. The
readout standardizes features and targets using 12,146 training genes and
chooses ridge alpha 1 using 1,350 validation genes. It does not fit on the test
genes or refit on the combined training and validation set.

Independent CPU fitting reproduces predictions within 6.96e-10 absolute error,
and SciPy ranks reproduce all three returned GTEx point estimates. GPU inference
was not rerun during this audit. The extraction review records the runtime
controls, unchanged features, and remaining execution-provenance gaps. The
shared split retains its previously documented eight pseudoautosomal test
windows identical to training/validation windows; this return does not alter
the cohort.

## Confidence intervals and scope

The original returned intervals remain byte-preserved in `results.csv`, the
audit reports, and `entry.json`'s `sourceCI`. They resample held-out genes with
fixed tissue queries and a fixed fitted readout. The website continues to omit
all tissue-identification intervals from charts, result details and CSV exports
because their provenance differs across rows. `entry.json` therefore sets
`uncertainty` to null. Improved interval estimation is deferred; no new interval
method or numerical bound has been substituted.

The return also contains maximum- and random-tissue-contrast correlations.
Those source records are retained here but are not additional endpoints in
the website's eight-task table. The existing scoring code automatically
incorporates the rounded 21.6% tissue value into Evo2's Biological context
category, with the existing fixed anchors and category weights.

## Archive contents

- `entry.json` is the website's source mapping; `primaryScale: 100` converts
  the returned retrieval fraction to percent. Its exact percent agrees with
  the independent audit's 11/51 calculation to floating-point precision.
- `returned/` contains anonymous review copies of result records, protocols,
  extraction code, completion records and numerical runtime checks. Personal
  paths, execution identifiers and redundant process-specific logs are omitted.
- `audit/` preserves the independent findings and numerical reports, with
  local paths anonymized. Historical audit findings describe the original run.
- `sources/evaluation/` contains all seven frozen evaluation scripts whose
  hashes match the refreshed `returned/final_evaluation/COMPLETE.json`.
- `SHA256SUMS.json` hashes every file in this compact archive except itself.

Large embeddings, predictions, bootstrap arrays, checkpoint/state files and
the original handoff data are not duplicated in this website checkout. Their
hashes remain in `returned/RETURN_MANIFEST.json` and completion records. The
original ZIP SHA256 is
`4572ece88daa9f448ca9b7d81a2182d5ca26e5b5287e6798aa38ef1c2cb8c253`.

The audit script accepts `EVO2_RETURN_DIR`, `EVO2_RETURN_ZIP`, and `EVO2_HANDOFF_DIR` for a complete return package and the frozen handoff. It cannot rerun from this compact archive alone. Included text hashes and byte sizes are refreshed after sanitization; absent numerical arrays, checkpoints and the original ZIP retain their original hashes. The numerical results and evaluation protocol are unchanged. The recorded successful historical manifest check applies to the original 25-entry return; the review manifest omits redundant execution logs.
