# Evo2 GTEx metric review — 2 November 2026

Conditional on acceptance of the extraction/provenance review, this return supplies the missing Evo2 20B tissue-identification result: **21.5686% (11/51 tissue queries)**, with the frozen 95% whole-gene percentile-bootstrap interval **7.8431–21.5686%**. The accompanying maximum-contrast Spearman is **0.605121 [0.593382, 0.616722]**, and random-contrast Spearman is **0.468919 [0.460332, 0.477364]**. All three use the same fitted predictions; they are not three independent inference runs.

## What the score and intervals mean

- Each of the 51 predicted tissue profiles is a vector across the same 5,782 held-out genes. Its Spearman correlation is calculated against every measured tissue profile; the highest correlation selects a tissue. Tissue queries receive equal weight. Ties within absolute 1e-12 receive fractional credit. The observed point has 11 untied correct queries.
- This is not a gene-level classification accuracy. It holds out genes within represented tissues, and does not test transfer to unseen tissues or individual genotypes. Retrieval does not subtract each gene's mean across tissues.
- The original split has 5,786 test genes; four lack complete reference coverage, yielding the frozen 5,782-gene common evaluation. The readout uses 12,146 training and 1,350 validation genes, training-only feature/target scaling, one shared ridge penalty across 51 heads, and no refit on validation. The selected penalty here is 1.0.
- The 10,000 saved bootstrap draws resample whole genes, retaining all tissue values together and keeping all 51 queries/candidates fixed. Ranks are recomputed exactly under duplicated-gene multiplicities. Bounds are the 2.5th and 97.5th percentiles. All returned draws are finite, with no constant-profile exclusions.
- These are pointwise intervals conditional on the fitted predictor, fixed tissue set and saved biological data. They do not cover donor resampling, model fitting/training randomness, runtime uncertainty, or multiplicity across models/tasks. The 1/51 = 1.9608% chance anchor is an exact uniform-choice expectation, not an empirical confidence interval.
- Maximum contrasts use the frozen tissue partner with the largest measured difference for each gene/query; this is a retrospective observed-contrast evaluation, not prospective tissue selection. Random contrasts use the supplied frozen random partners.

## The asymmetric retrieval interval is reproducible

The saved retrieval distribution has median **7/51 = 13.7255%** and mean **14.6331%**, versus the full-data point of 11/51. Among 10,000 draws, **9,617 are below the point, 291 equal it and 92 exceed it**. The distribution spans 2–15 correct tissues; its percentile limits are 4 and 11. The upper endpoint equalling the point is therefore not a rounding or interval-transcription error.

Independently expanded 128 gene-bootstrap draws selected with `np.random.default_rng(20261102).choice(10000, 128, replace=False)`, ranked the duplicated prediction/truth rows using SciPy, and recomputed all 51-by-51 correlation matrices. All 128 retrieval results matched the saved draws exactly. This review did not execute returned evaluation code.

Seven of the 11 correct full-data tissue queries have a self-versus-best-other Spearman margin below 0.004. For example, cerebellar hemisphere has margin 0.000338 and pancreas 0.000428. In the 128 independent draws, their correct-match frequencies were 88/128 and 43/128; Testis and Whole Blood remained correct in all 128. These fragile maxima and the discrete top-1 statistic provide a plausible explanation for the downward-shifted bootstrap distribution. This numerical check does not establish nominal coverage of a percentile interval for this nonsmooth statistic. Preserve the frozen interval; do not symmetrize it or substitute a binomial interval over supposedly independent tissues.

## Integration scope if accepted

The current local website still marks `evo2_20b/tissue_identification` as unevaluated; the archived manuscript Table 1 has a dash. This return matches that endpoint/cohort and would display as **21.6** at current table precision. Existing Evo2 values on the other seven website endpoints are different experiments and should not be replaced.

The original handoff explicitly maps `retrieval_top1` to the missing Table 1 cell and tissue-identification figure, `maximum_contrast_spearman` to the tissue-contrast figure, and `random_contrast_spearman` to supplementary/diagnostic evidence. Between-model comparisons and figure redraws were intentionally outside the collaborator pipeline; its `paired_differences.csv` is empty. The saved common bootstrap draws permit paired comparisons locally if a later manuscript claim needs them. Pointwise intervals alone do not establish model ranking.

Descriptively, 21.6% lies above the website's GENERATORv2 17.6%, CENO 9.8%, and pre-trained NTv3 7.8% values, and below the smallest native-output NTv3 value of 27.5%; this is not a significance conclusion. The new run does not overturn the existing manuscript's high AlphaGenome/NTv3 post-trained tissue scores or its represented-tissue caveat.

The website currently omits tissue confidence intervals for all rows because their provenance varies; an eventual addition should respect or deliberately review that common display policy. It should also remove the outdated incomplete-Evo2 missing reason and update the site's data counts and exploratory reference index through its normal build/update path. No website, manuscript, remote repository or GPU job was changed by this review.

The prior audit's eight test rows with byte-identical X/Y pseudoautosomal input windows in training/validation are inherited from the common frozen split. Index separation does not establish sequence uniqueness. Any future sensitivity analysis should use a common cohort across models, not change Evo2 alone. This issue is distinct from FP8 execution acceptance.

## Source paths

- Returned metrics and draws: `evo2-results/final_evaluation/evaluation/{results.csv,protocol.json,evo2_20b_bootstrap.npz}` beneath this audit directory.
- Returned readout and point matrix: `evo2-results/final_evaluation/evo2_20b/{protocol.json,predictions.npz,retrieval_confusion.csv}`.
- Original definitions and intended outputs: `output/evo2-collaborator-handoff-stopped-20260923/evo2-gtex-handoff/PROTOCOL.md` and `scripts/evaluation/evaluate_evo2.py` within that handoff.
- Current public-package metric implementation: `bend2-benchmark/src/bend2/_tasks/tissue_identification.py`.
- Website state/policy: `genomic-bending-leaderboard/data/{benchmark.json,evaluation-updates.json,sources.md}`; mirrored website under `bend2-benchmark/website/`.
- Archived manuscript evidence: `genomic-bending-leaderboard/provenance/{table-1.tex,table-1-source-records.csv,main-text-definitions.tex}`. This is the website's archived manuscript snapshot, not a newly fetched Overleaf state.
- Earlier BF16 diagnostic and inherited duplicate-input issue: `output/evo2-return-audit-20261031/{audit-summary.txt,duplicate-input-audit.json}`.
- Machine-readable descriptive statistics from this review: `metric-review-stats.json` in this directory.

All paths above are relative to `/Users/fvk220/Documents/New project` unless described as relative to this audit directory.
