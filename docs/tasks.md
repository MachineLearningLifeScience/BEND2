# Choose a task

BEND 2.0 has eight tasks across five capabilities. `atlas_profile` is a useful
first task: it uses short sequences and includes its data.

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

Seven tasks use frozen embeddings; `prior` needs nucleotide probabilities.
You can run any supported subset. Unrun tasks are recorded as missing.

## Plan a run

Inspect your adapter before starting a long run:

```bash
bend2 plan my_model.py --tasks siraj
bend2 run my_model.py --tasks siraj --output results/my-model
```

`siraj` selects the four related regulatory tasks together: `context`,
`background`, `repair_percentile` and `cell_selective`. Use individual task IDs,
a comma-separated list, or `all`. The default is `atlas_profile`. `all` records
incompatible tasks as skipped; requesting one by name stops the run before
data downloads.

Planning lists input lengths, model limitations, missing dependencies and
downloads. It imports your adapter but does not call it or download data.
Load weights on first inference. In Python, `bend2.plan(model, tasks="all")`
returns the plan as a dictionary.

The core package and statistical readouts run on CPU. Your encoder determines
whether inference needs a GPU. Runtime depends on model size, feature dimension,
context length and hardware.

| Task | Scale | First-run data | Practical use |
|---|---|---|---|
| `atlas_profile` | 7,657 distinct 145-base sequences | Included | Short sequences; CPU baseline available |
| `prior` | 512 evaluation windows, 1,200 bases each | Included | Small, but requires nucleotide probabilities |
| `context` | 170,292 substitutions; 128 elements | 93 MB Siraj download, shared below | Start here for cell-dependent effects |
| `background` | 68,026 paired mutations; 114 elements | Same Siraj data | Reuses Siraj embeddings and fitted readouts |
| `repair_percentile` | 331 targets; 110 elements | Same Siraj data | Reuses Siraj embeddings and fitted readouts |
| `cell_selective` | 167,958 eligible substitutions; 127 loci | Same Siraj data; compact outcome table included | Reuses Siraj embeddings and fitted readouts |
| `opensplice` | 590,104 interventions; 466 genes | 425 MB OpenSplice download | Largest currently packaged assay |
| `tissue_identification` | 5,782 held-out genes; 51 tissues; 131,072-base inputs | 835 MB human reference assembly | Requires the `genome` extra and an encoder that handles the full context |

Assay rows and unique DNA sequences are different counts. Reference sequences
repeat across interventions; BEND embeds each unique sequence once within a
shared dataset. Siraj has 169,912 distinct sequences of 189–200 bases;
OpenSplice has 590,703 distinct sequences of 77–245 bases.
Request the four Siraj tasks together to share that work.
Allow additional disk space for preparation and embeddings. A float32 matrix
alone costs `number_of_sequences × feature_dimension × 4` bytes; preparation
files and cache metadata require additional space.

Tissue identification requires the full 131,072-base input and the `genome` extra:

```bash
python -m pip install "bend2[genome] @ git+https://github.com/MachineLearningLifeScience/BEND2.git@main"
```

## What stays fixed

For embedding tasks, BEND fits a readout on frozen representations and evaluates
it using the task's biological holdout. These results measure the fitted readout;
native prediction heads use separate evaluation procedures.

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
  Both target cells are evaluated and loci receive equal weight. Measured outcomes
  are used only after selection.
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

Compare scores within each task, using its units and direction. The package
reports separate task scores. Experimental references measure reproducibility
or transfer for particular assays and should not be interpreted as universal ceilings.

Training exposure, allowed sequence context, pooling, and native versus fitted
interfaces matter when comparing models. Keep those declarations with the
results, as described in [the model guide](models.md).

See [data and licenses](data.md) for source attribution, terms and offline use.
