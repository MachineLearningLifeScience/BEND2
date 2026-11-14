# Table 1 background interaction: independent repeat evaluation

This extends the exact Figure 4 protocol of 11 November to every populated background-interaction entry in Table 1. It updates the evaluation measurements, not the fitted heads, model weights, biological holdouts or prediction interfaces.

All models and the experimental reference use the same 68,026 paired edits at 114 Siraj regulatory elements. Compute each repeat's activity as log2((RNA+0.5)/(DNA+0.5)), take the four-genotype interaction A−A0−R+R0, and average HepG2 and K562. Divide the five repeats into all ten disjoint pairs of a two-repeat pool and a three-repeat pool. For each model, calculate Spearman correlation against each pool within each locus, average all twenty correlations within that locus, and then average loci equally. The experimental reference averages the ten correlations between independent pools. These overlapping partitions are not treated as independent observations.

Pointwise 95% confidence intervals use 20,000 paired bootstrap samples of whole loci, with seed 20261111. All 114 loci have defined scores for every row. No effect-size selection is used in this endpoint. The separate 89-locus strong-interaction figure is not the Table 1 endpoint.

Fitted heads remain trained on the published pooled-assay target estimator with complete-element holdouts. Native AlphaGenome uses accessibility 501 bp; native Enformer uses DNase 1024 bp; native NTv3 uses DNase 501 bp log-coverage. The exact historical canonical-label point estimate is replayed for every newly scored model before accepting its new score. In particular, the matched-penalty NTv3 heads used in the strong-interaction figure do not replace the original Table 1 heads.

The new experimental reference is independent repeat agreement. It replaces the old within-repeat HepG2–K562 transfer reference. It is not a ceiling: both sides of the experimental reference have measurement noise, whereas a model comparison has noise only on the experimental target side.

## Reproduction and storage

`analyze.py` runs on remote compute environment with the existing archived raw counts and prediction tables. No GPU inference is required. Additional paired prediction inputs are copies of existing validated local result files, listed in `input/local-sources.json`; their locations are supplied through `--input-dir`.

Evo2, k-mer, ResNet and the matched random control retain their already-validated results from the exact same protocol run on 11 November. Their source receipt, original-label replay checks and source SHA256 hashes are embedded in `VALIDATION.json`. The native AlphaGenome, Enformer, NTv3 650M post and experimental-reference scores are recomputed again and required to match that run's scores and interval endpoints within 1e-12.

`table-ready.csv` contains the 15 populated model/readout entries plus experimental reference, using the manuscript CSV model IDs. `summary.csv` also includes the random-network figure control. `per-locus.csv` contains the newly scored per-locus values; bulk raw measurements and predictions remain remote. `VALIDATION.json` records coverage, provenance and replay errors.
