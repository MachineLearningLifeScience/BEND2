# Choose a task

BEND 2.0 measures eight endpoints across five capabilities. Start with
`atlas_profile`: it uses short sequences, includes its data, and exercises the
same model interface as the larger fitted-readout tasks.

| Capability | Task ID | What your model needs to do | Score · better direction |
|---|---|---|---|
| Sequence priors | `prior` | Recover a hidden nucleotide from its sequence context | Conditional log loss, bits/base · ↓ |
| Functional prediction | `opensplice` | Predict how a mutation changes splicing | Macro-gene Spearman correlation · ↑ |
| Biological context | `context` | Predict the HepG2-minus-K562 difference in a mutation's effect | Macro-element Spearman correlation · ↑ |
| Biological context | `tissue_identification` | Match a predicted expression profile to one of 51 tissues | Top-1 identification accuracy, % · ↑ |
| Genetic interactions | `background` | Predict how the same mutation's effect changes between parental backgrounds | Macro-element Spearman correlation · ↑ |
| Genomic design | `repair_percentile` | Select one mutation that brings an element toward a requested response | Measured residual midrank percentile, 0–100 · ↓ |
| Genomic design | `cell_selective` | Select an edit that changes a target cell while limiting the effect in the other cell | Measured cell-selective utility, log₂ · ↑ |
| Genomic design | `atlas_profile` | Select sequences for requested combinations of active and inactive cells | Measured gain over intent-matched random selection, log₂ · ↑ |

All eight endpoints have runners. Seven use frozen embeddings; `prior` needs
nucleotide probabilities. A model can contribute a subset. Missing tasks stay
visible in the saved results and are never treated as failed models or zeros.

## Plan a run

The core package and statistical readouts run on CPU. Your encoder determines
whether inference needs a GPU. Runtime depends strongly on model size, feature
dimension, context length, and hardware; the counts below are more useful than
an unmeasured wall-clock estimate.

| Task | Scale | First-run data | Practical use |
|---|---|---|---|
| `atlas_profile` | 7,657 distinct 145-base sequences | Included | First real run; no external assay download |
| `prior` | 512 evaluation windows, 1,200 bases each | Included | Small, but requires nucleotide probabilities |
| `context` | 170,292 substitutions; 128 elements | 93 MB Siraj download, shared below | Start here for cell-dependent effects |
| `background` | 68,026 paired mutations; 114 elements | Same Siraj data | Reuses Siraj embeddings and fitted readouts |
| `repair_percentile` | 331 targets; 110 elements | Same Siraj data | Reuses Siraj embeddings and fitted readouts |
| `cell_selective` | 167,958 eligible substitutions; 127 loci | Same Siraj data; compact outcome table included | Reuses Siraj embeddings and fitted readouts |
| `opensplice` | 590,104 interventions; 466 genes | 425 MB OpenSplice download | Largest currently packaged assay |
| `tissue_identification` | 5,782 held-out genes; 51 tissues; 131,072-base inputs | 835 MB human reference assembly | Requires the `genome` extra and an encoder that handles the full context |

Assay rows and unique DNA sequences are different counts. Reference sequences
repeat across interventions; BEND embeds each unique sequence once within a
shared dataset. Request the four Siraj tasks together to share that work.
Allow additional disk space for preparation and embeddings. A float32 matrix
alone costs `number_of_sequences × feature_dimension × 4` bytes; preparation
files and resumable shards add overhead.

## What stays fixed

For embedding tasks, your model supplies frozen representations. BEND fits
the prescribed readout and evaluates it under the task's biological holdout.
This is a **fitted-readout result**. It does not become a native prediction-head
result because the underlying architecture also has a native head.

- **OpenSplice:** five folds hold out whole genes. Mutant-minus-reference
  effects are scored within each held-out gene, then averaged equally over
  genes.
- **Cell contrast:** five folds keep each complete element and its related
  backgrounds together. The target is the paired HepG2-minus-K562 effect.
- **Background interactions:** compare the same mutation across parental
  backgrounds; preserve the element holdout and average elements equally.
- **Repair:** select from the fixed one-edit menu, excluding direct reversion.
  The measured residual is ranked against the same request's alternatives.
  A lower percentile is better; it is not an effect size or success rate.
- **Cell-selective editing:** select using predicted target-cell effect minus
  the absolute predicted off-target-cell effect, with no edit available.
  Nominations are fixed before measured outcomes are used for scoring. Both target cells
  are evaluated and loci receive equal weight.
- **Atlas:** fit on 5,246 source constructs, separate from 2,411 candidate
  sequences and their families. Select ten sequences for each of 16 requests
  across twelve cells. Score their measured gain over intent-matched random
  selection in each of two replicates. These replicate values are descriptive,
  not a confidence interval.
- **Sequence priors:** hide the central nucleotide of 512 human reference
  windows from distinct 1-Mb blocks. Return four conditional probabilities
  in A/C/G/T order. Baseline fitting uses a separate 1,024-window panel.

Tissue identification holds out 5,782 genes, with 12,146 training and 1,350
validation genes. It matches tissue profiles across genes among 51 represented
tissues; it is not a test of transfer to unseen tissues. Inputs are forward
reference-genome windows centered on the prescribed transcription start site.

## Read scores in context

Scores keep their own units and direction. BEND does not combine them into
an overall score. Missing tasks and undefined metrics remain visible.
Experimental references describe reproducibility or transfer under a specific
measurement construction; they are not universal ceilings.

Training exposure, allowed sequence context, pooling, and native versus fitted
interfaces matter when comparing models. Keep those declarations with the
results, as described in [the model guide](models.md).

## Data sources

| Data | Primary source | Terms |
|---|---|---|
| OpenSplice | [Figshare version 5](https://doi.org/10.6084/m9.figshare.32337414.v5) | CC BY 4.0 |
| Siraj saturation mutagenesis | [Zenodo record 15297965](https://doi.org/10.5281/zenodo.15297965) | CC BY-NC 4.0 |
| Atlas of AI-designed enhancers | [Zenodo version 0.2](https://doi.org/10.5281/zenodo.17410822) | CC BY 4.0 |
| Human reference prior panel | [UCSC GRCh38/hg38 assembly](https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/README.txt) | Upstream reference attribution applies |
| Tissue expression | [GTEx Portal](https://gtexportal.org/home/downloads/adult-gtex/bulk_tissue_expression) | GTEx source terms apply |

The software license does not replace dataset terms. In particular, the Siraj
data carry a noncommercial condition. Data downloads are pinned and verified;
packaged derived data retain their attribution and provenance.
See [data and caching](data.md) for complete notices and acquisition details.
