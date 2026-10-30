# DRAFT leaderboard data snapshot

This directory preserves the manuscript's **Table 1**, with audited website additions recorded separately in `evaluation-updates.json`. The manuscript title is **Benchmarking the Capabilities Needed to Design DNA**; DRAFT expands to **DNA Design Readiness Across Functional Tasks**. “Genomic Bending” is an older project name.

- Manuscript revision: `1abee7c638616c578b2fea497e63b59e68752c01` (clean working tree at extraction).
- Extracted: 22 October 2026.
- Primary table: `tables/bend2-reference-main.tex`.
- Table SHA-256: `75febce7f238262b435731ba8258f7f647111a6edf83f430f2099ada3eb5c471`.
- Source records: `tables/bend2-main-benchmark.csv`.
- Records SHA-256: `332d38d328592db946c336c0260d62c4aa02c9be005636e29bea5054fa743c28`.
- The exact copied source files and their hashes are listed in [the audit](../provenance/audit.json).

`benchmark.json` contains 17 model/interface rows, eight endpoints, five capability categories, 111 manuscript model values, two shared checkpoint priors, one new CENO evaluation, and seven experimental-reference values. The five dataset groups represented here are GRCh38, OpenSplice, Siraj, GTEx and the enhancer Atlas: one reference genome and four experimental resources. The manuscript's broader experiments include additional datasets.

## Values and interfaces

`value` and `displayValue` preserve the displayed manuscript precision, including ties. For manuscript entries, `sourceValue` preserves the matching precise CSV estimate. All 144 archived table positions (18 rows including the reference, by eight endpoints) are checked against the original CSV. Website additions retain their own explicit source mapping. Missing entries retain `unsupported` or `unevaluated` status and are never replaced with zero.

The primary AlphaGenome row is `alphagenome_fitted`; `alphagenome` is its native-output row. Native rows for NTv3 are separate from their fitted hidden-representation rows. Enformer uses native functional outputs. **All four of these native-output pipelines fit a linear head to native features for multi-cell selection.** Their cell-selective native outputs also use held-locus calibration slopes. “Native” must not be interpreted as zero-shot throughout the table.

Source confidence intervals are retained only when a matching CSV row supplies both limits, contains its source point, and identifies the appropriate biological sampling unit. They remain task-level, reported pointwise intervals. They do not quantify uncertainty in the reference index, and they do not establish a between-model ranking. Tissue-identification intervals are not exported because their provenance differs across rows. Multi-cell repeats are descriptive values, not confidence intervals.

## Coverage audit, 27 October 2026

The two post-trained NTv3 checkpoints already had hidden-base evaluations. Their native-functional rows now show the same values (100M: 1.492; 650M: 1.375), with identical source estimates and intervals. Checkpoint revisions were checked against the native-head inventory; `sharedFrom` identifies each source row. These are shared measurements, not new inference runs. Their combined scores now include the Prior category.

CENO's missing full OpenSplice evaluation is now complete: **0.2954435032 Spearman**, with a 95% gene-bootstrap interval of **0.2815974629–0.3089228028**. All 590,703 sequence embeddings were recomputed uniformly in FP32, covering 590,104 interventions and 466 genes. The original five gene folds and readout settings are unchanged. Independent checks verified the model implementation, feature coverage, predictions, correlations and intervals. The [evaluation archive](../provenance/coverage-20261027/ceno-opensplice/README.md) includes the executed code and checksums. A separate converged ridge solve gives 0.303205; the table retains the published solver tolerance for consistency with the existing rows.

AlphaGenome has no nucleotide-probability head, including when its functional representations receive fitted readouts. Enformer has neither nucleotide probabilities nor native splice outputs. Evo2 tissue embeddings remain incomplete and are pending at the user's request. Missing-cell dialogs give these reasons.

DNABERT-2's older prior experiments scored entire BPE tokens. A new, explicitly defined single-base query was evaluated on LUMI using all 512 frozen genomic blocks. It forces singleton outputs where native tokenization uses multi-base tokens in all 512 cases, retaining a median 0.000002964 of the original vocabulary probability mass before renormalization. The resulting 6.203 bits/base is archived as a query diagnostic, **excluded from the table and combined score**. This is an interface limitation, not a conclusion about the model's sequence knowledge. The [query audit](../provenance/coverage-20261027/dnabert2-prior/README.md) includes source code, probabilities, checkpoint hashes and numerical checks.

`evaluation_updates.py` applies the documented additions after a snapshot build and can also be run independently. It never edits the archived manuscript CSV or LaTeX table.

## Reference-index audit

The site-defined **Reference index** is exploratory and is not a metric reported in the paper. Each task score is `100 × (value − baseline) / (NTv3 650M post − baseline)`. This handles both metric directions. Average available endpoints within each category, then available categories equally. Do not clamp: scores below 0 or above 100 remain meaningful relative to the stated anchors. Models with missing tasks receive partial scores. Tooltips and CSV exports include task and category coverage. Missing values never count as zero.

The index (`reference-index-v2`) uses eight endpoints across five categories, including Sequence priors. Prior loss uses the empirical base-composition baseline of 1.974 bits/base and the fixed NTv3 650M post reference of 1.375 bits/base; lower loss gives a higher score. Prior scores use different probability interfaces, and many functional models do not report them. The native-functional NTv3 rows share the prior evaluation of their identical post-trained checkpoints; this is the same nucleotide-probability head, not an estimate inferred from downstream performance. When prior loss is unavailable, the combined score averages the other available categories.

| Endpoint | Zero-point baseline | Scientific meaning |
| --- | ---: | --- |
| Prior loss | 1.974 bits/base | Reported empirical base-composition loss on the frozen panel; not the 2-bit uniform prior. |
| Splicing effects | 0 correlation | Expected independent rank-order correlation. A constant predictor has undefined Spearman correlation; zero is a null anchor, not a measured constant baseline. |
| Cell contrast | 0 correlation | Same independent-rank null interpretation. |
| Tissue identification | 100/51% | Exact equal-weight uniform choice among 51 tissues; displayed as 2.0%. |
| Background interaction | 0 correlation | Same independent-rank null interpretation. |
| Single-edit rank | 50 percentile | Exact expected measured midrank under uniform candidate selection; lower is better. |
| Cell selectivity | 0 utility | The protocol explicitly defines `U(no edit)=0`; primary `λ=1`. |
| Multi-cell gain | 0 gain | The endpoint subtracts exact intent-matched random utility; this is not zero absolute utility. |

The NTv3 650M post row is a fixed 100-point reference, not an upper bound. The experimental measurements are **not normalization anchors and not ceilings**. In particular:

- OpenSplice's repeat reference shares the wild-type PSI estimate across repeat-specific effects.
- Cell contrast uses disjoint RNA/DNA subsets on 127 of 128 loci; model endpoints use pooled posterior effects.
- Tissue identification averages both donor-half directions on the same 5,782 genes and 51 tissues.
- Background interaction uses **HepG2–K562 transfer, 0.421**, matching the current table and Figure 4A. Earlier replicate-subset references are superseded.
- Single-edit and cell-selective references select on one repeat subset and evaluate on the other; measurement aggregation differs from the model endpoints.
- Multi-cell references select on one RNA repeat and evaluate on the other, reciprocally, over overlapping programs.

Positive multi-cell gain does not imply that the requested expression program was achieved. The manuscript reports AlphaGenome fitted at **0.833 gain** but **−0.096 absolute utility**; native-output AlphaGenome has **0.707 gain** and **−0.222 absolute utility**.

## Supplementary values

`supplementary.multiCellRepeats` includes repeat measurements only where their mean matches a current Table 1 source point. Those markers are not uncertainty intervals. The repair-budget series is a separately labeled archived source curve for success versus number of candidates tested; it covers a subset of the current model roster plus an explicit uniform-selection control. Each included model's companion residual-rank estimate matches the current Table 1 precise value. The curve is not the Table 1 residual-rank endpoint. Retired models from the archived source are omitted.

`supplementary.repairBudgets.experimentalReference` preserves the paper’s separate experimental selection curve for the same 331 targets in 110 elements. It selects using RNA subsets 1–2 and evaluates on 3–5, then swaps their roles; it retains the original pooled-data target eligibility and success tolerances. Its 95% intervals bootstrap whole elements after averaging requests and directions. The reference is not a ceiling and is not included in the combined score. The exact source CSV is copied to `provenance/repair-budget-reference.csv` (SHA-256 `6f2cb289cfebfd538e946193fb49730a88316687740a952f35d6b6d93f979d60`).

Official capability colors are copied from `capability-style.tex`: sequence priors `#9C7524`, functional prediction `#2463A6`, biological context `#19836E`, genetic interactions `#7956A5`, genomic design `#BE4D35`.

## Links and reproduction

The public [BEND 2.0 dataset release on Hugging Face](https://huggingface.co/datasets/yhsure/BEND2) provides the evaluation data. The files in this directory preserve the website’s result snapshot and provenance. Original dataset references remain linked on the site for attribution.

No verified public BEND 2.0 paper URL is available. **Do not use arXiv:2610.11761**: it identifies *RAGenome: Scaling Retrieval-Based Genomic Language Models to Long Contexts*, a different paper. The manuscript points to the planned `machinelearninglifescience/BEND2` repository; the current working code is on [yhsure/genomic-bending’s benchmark branch](https://github.com/yhsure/genomic-bending/tree/benchmark). Original dataset links come from the manuscript bibliography.

To reproduce the snapshot, run:

```sh
python3 data/build_snapshot.py /absolute/path/to/the/manuscript
```

The script reads the manuscript, checks the display table against its source CSV, copies exact source snapshots into `provenance/`, and writes the data and audit. It does not modify the manuscript or run models. Changed table layouts, row ordering or metric definitions require manual review of the parser and metadata before a new snapshot is accepted.
