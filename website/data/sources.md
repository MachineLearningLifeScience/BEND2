# DRAFT leaderboard data snapshot

This directory freezes the current manuscript's **Table 1**, not a new model evaluation. The manuscript title is **Benchmarking the Capabilities Needed to Design DNA**; DRAFT expands to **DNA Design Readiness Across Functional Tasks**. “Genomic Bending” is an older project name.

- Manuscript revision: `1abee7c638616c578b2fea497e63b59e68752c01` (clean working tree at extraction).
- Extracted: 22 October 2026.
- Primary table: `tables/bend2-reference-main.tex`.
- Table SHA-256: `75febce7f238262b435731ba8258f7f647111a6edf83f430f2099ada3eb5c471`.
- Source records: `tables/bend2-main-benchmark.csv`.
- Records SHA-256: `332d38d328592db946c336c0260d62c4aa02c9be005636e29bea5054fa743c28`.
- The exact copied source files and their hashes are listed in [the audit](../provenance/audit.json).

`benchmark.json` contains 17 model/interface rows, eight endpoints, five capability categories, 111 reported model values and seven experimental-reference values. The five dataset groups represented here are GRCh38, OpenSplice, Siraj, GTEx and the enhancer Atlas: one reference genome and four experimental resources. The manuscript's broader experiments include additional datasets.

## Values and interfaces

`value` and `displayValue` preserve the displayed manuscript precision, including ties. `sourceValue` preserves the matching precise CSV estimate; the experimental arrays have not been rerun. Every one of the 144 table positions (18 rows including the reference, by eight endpoints) is checked against the CSV for matching missingness and rounding. Missing entries retain `unsupported` or `unevaluated` status and are never replaced with zero.

The primary AlphaGenome row is `alphagenome_fitted`; `alphagenome` is its native-output row. Native rows for NTv3 are separate from their fitted hidden-representation rows. Enformer uses native functional outputs. **All four of these native-output pipelines fit a linear head to native features for multi-cell selection.** Their cell-selective native outputs also use held-locus calibration slopes. “Native” must not be interpreted as zero-shot throughout the table.

Source confidence intervals are retained only when a matching CSV row supplies both limits, contains its source point, and identifies the appropriate biological sampling unit. They remain task-level, reported pointwise intervals. They do not quantify uncertainty in the reference index, and they do not establish a between-model ranking. Tissue-identification intervals are not exported because their provenance differs across rows. Multi-cell repeats are descriptive values, not confidence intervals.

## Reference-index audit

The site-defined **Reference index** is exploratory and is not a metric reported in the paper. Each task score is `100 × (value − baseline) / (NTv3 650M post − baseline)`. This handles both metric directions. Average available endpoints within each category, then available categories equally. Do not clamp: scores below 0 or above 100 remain meaningful relative to the stated anchors. Models with missing tasks receive partial scores. Tooltips and CSV exports include task and category coverage. Missing values never count as zero.

The index (`reference-index-v2`) uses eight endpoints across five categories, including Sequence priors. Prior loss uses the empirical base-composition baseline of 1.974 bits/base and the fixed NTv3 650M post reference of 1.375 bits/base; lower loss gives a higher score. Prior scores use different probability interfaces, and many functional models do not report them. When prior loss is missing, the combined score averages the other available categories without imputing a score from another interface.

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

No verified public DRAFT paper URL is supplied by the manuscript. **Do not use arXiv:2610.11761**: that page was checked and identifies *RAGenome: Scaling Retrieval-Based Genomic Language Models to Long Contexts*, a different paper. The code URL in the manuscript is `https://anonymous.4open.science/r/draft-5709`; its availability is not asserted here. Dataset links come directly from the manuscript bibliography and are labeled as such in the JSON.

To reproduce the snapshot, run:

```sh
python3 data/build_snapshot.py /absolute/path/to/the/manuscript
```

The script reads the manuscript, checks the display table against its source CSV, copies exact source snapshots into `provenance/`, and writes the data and audit. It does not modify the manuscript or run models. Changed table layouts, row ordering or metric definitions require manual review of the parser and metadata before a new snapshot is accepted.
