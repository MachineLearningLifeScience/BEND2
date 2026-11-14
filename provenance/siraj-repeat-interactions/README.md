# Independent-repeat interaction evaluation

This is the current manuscript's background-interaction endpoint. It replaces
the pooled-target evaluation and its cross-cell reference. The original October
Table 1 files remain historical; current values are in `table-ready.csv` and
`data/benchmark.paper.json`.

`PROTOCOL.md` defines the 68,026-paired-edit, 114-element endpoint. `table-ready.csv`
contains all 15 model/readout values and the experimental reference, 0.3893995481.
`VALIDATION.json` records exact replay of the former metric and agreement with
an independently checked repeat analysis. `INPUT-RECEIPT.json` hashes the raw-count
source and compact five-repeat table. The runtime scorer is
`src/draft/_tasks/background.py`; its evaluation inputs never enter readout fitting.

To recreate the bundled repeat table from the original paired count archive:

```bash
python build_repeat_asset.py evaluation-input.parquet siraj-interaction-repeats.parquet
```

The input contains the four genotype counts for five repeats in HepG2 and K562.
Its exact source hash is recorded in `INPUT-RECEIPT.json`. The bundled table keeps
only edit identities and five float64 cell-averaged interactions, with no model
predictions. `reproduce_table.py --help` describes replaying the historical model
comparison from archived predictions; ordinary package users can evaluate their
own embeddings with `draft run my_model.py --tasks background`.

The separate strong-interaction analysis selects using repeats 1–3 and evaluates
using repeats 4–5. Its 89-element cohort is not used for Table 1.

`components/` retains the executed single/combined/interaction and strong-subset
analysis, its protocol, compact result table and membership/source hashes. Its
inputs are the original paired count/prediction archive and independently fixed
selection files; these large research inputs are not duplicated here.

The strong subset can be reconstructed directly from the bundled repeat table:

```bash
python components/select_strong.py ../../src/draft/_data/siraj-interaction-repeats.parquet membership.parquet
```

Run this command from `provenance/siraj-repeat-interactions/`. Selection centers
each repeat within its element, then uses only repeats 1–3: absolute mean at
least 0.5 log₂ and consistent sign. It recovers 6,136 selected edits at 89 elements;
the matched all-edit cohort contains 53,101 edits. Repeats 4–5 never select edits.

### Research-archive inputs

The core package is self-contained once the documented Siraj source ZIP is
available: the independent-repeat evaluation table is bundled and checksum
verified. `components/select_strong.py` also runs directly on that bundled table.

The historical `reproduce_table.py` and `components/analyze.py` are research
replay scripts. They use NumPy, pandas and SciPy only, with paths supplied by
command-line arguments; all helper functions are included. They additionally
require the original saved model predictions and paired raw-count archive.
`build_repeat_asset.py` converts that paired archive; it does not reconstruct
its four-genotype rows directly from ENCODE FASTQ/count downloads. That upstream
assembly is not included here. The archive schema requires edit identity fields,
`context_id`, and `{R,R0,A,A0}_{rna,dna}{1,...,5}` count columns. Exact input hashes
are recorded. The small prior-analysis receipts needed by the table replay are
included in `input/`; the six per-model Parquet prediction files must be supplied
in the chosen `--input-dir`. No private machine paths are required.
