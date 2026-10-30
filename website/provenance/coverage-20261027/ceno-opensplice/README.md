# CENO: held-out OpenSplice genes

**Accepted benchmark result: Spearman 0.2954435, with a 95% gene-bootstrap interval of 0.2815975–0.3089228.** This completes the missing CENO entry under the published evaluation pipeline.

The evaluation covers all 590,104 interventions in 466 genes, with complete genes held out in five folds. Every record's fold matches the archived NTv3 650M post evaluation. The frozen CENO representation has 1,024 dimensions, pooled from the final hidden layer over non-special tokens. The linear head uses alternate-minus-reference features, sequence-length difference, and training-fitted context and intervention-type indicators. It uses Ridge with alpha 10, an intercept, no normalization, and the published LSQR tolerance of 1e-4.

All 590,703 unique sequences were recomputed uniformly in FP32. The earlier partial CUDA cache was excluded because its BF16 features did not match the new extraction closely enough for safe mixing. The final extraction passed comparisons against CENO's released native implementation, including mutation differences, individual versus batched evaluation, permutation, and padding checks. Coverage, finite features, prediction order, fold identity, per-gene correlations and bootstrap intervals were independently verified.

## Numerical sensitivity

The published tolerance gives **0.2954435**. A separate solve at tolerance 1e-6 gives 0.3032191. Independent float64 Cholesky and LSQR at 1e-10 give **0.3032053324** and **0.3032052967**, respectively; their held-out predictions agree within 4.1e-7 relative error across all five folds. The direct solves also satisfy the ridge equations to numerical precision.

This is a solver-tolerance effect, not an implementation discrepancy. The benchmark retains **0.2954435**, using the same published pipeline as the existing rows. The converged result is archived as a numerical-sensitivity check, not substituted as a CENO-specific improvement. No model, feature, regularization, target or split settings were selected using the results.

## Files

`PRIMARY_RESULT.json` and `AUDIT.json` contain the primary score and its provenance. `opensplice_ceno_1b_1m.per_gene.csv` contains all 466 correlations. `FULL_PROTOCOL.json`, `full-pilot.json`, `ARCHIVED_FOLDS.json` and `opensplice_ceno_full.json` document extraction, coverage and split checks. `SOLVER_SENSITIVITY.json` and `convergence/` retain the numerical diagnostics separately.

`sources/` contains the exact executed scripts and relevant readout implementation files, fetched from LUMI and verified against execution hashes. `RUN_RECEIPT.json` records the successful GPU array 23220802, readout CPU job 23220803 and convergence job 23222148. The raw primary result is unchanged; the receipt supplies its CPU job ID, which the clean container environment omitted. `SHA256SUMS.json` covers this compact archive.

Full predictions and embeddings remain outside this archive. Primary and convergence predictions are retained locally under `../results/`; the full cache and shards remain under `/scratch/project_465003339/ajeppese/bend-ceno-opensplice-20261027` on LUMI. No manuscript or website files were modified by this evaluation.
