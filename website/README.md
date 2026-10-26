# Website

The website displays paper results and reviewed community submissions.

## Run locally

From the repository root, with the benchmark environment activated:

```bash
pip install -e .
npm --prefix website ci
npm --prefix website run dev
```

Open the printed local URL. To build the static site:

```bash
npm --prefix website run build
```

The output is `website/dist/`. Both commands first generate leaderboard data.
Node.js 22 or newer is required. If the active Python is elsewhere, set
`BEND2_PYTHON=/absolute/path/to/venv/bin/python` before the npm command. Restart
the development server after changing contribution JSON files. Set the paper
link in `index.html` when the publication URL is available.

## Leaderboard data

The build reads:

- `data/benchmark.paper.json`: the paper results.
- `../submissions/*.json`: community submissions.
- `../reviews/*.json`: matching rescoring and reproduction records.

To generate `data/benchmark.json` separately:

```bash
python website/scripts/build_leaderboard.py
```

The Python API is `bend2.submissions.build_leaderboard`. Arguments
`--reference`, `--submissions`, `--reviews` and `--output` set the input and output
paths. Every published submission must have a matching review.
Use `--preview` (or `BEND2_PREVIEW_SUBMISSIONS=1` with npm) only for PR previews;
all community results are labelled **Awaiting review**, including those with
proposed receipts. The build reads local JSON files; maintainer rescoring is
a separate step.

The output retains the paper data and adds community models and their evidence
links. Each model has eight task cells; unrun tasks have null values. Ranking
and display use each task's stated precision. `sourceValue` retains the
unrounded result. Always build from `benchmark.paper.json`.

## Frontend data

`data/benchmark.json` contains `models`, `measurements` and `sources` arrays.
Community records have the following fields:

- A model has `origin: "community"`, a public `url`, `submissionPath`, and its
  evaluated model `declarations`. Its model kind is `foundation`. Embedding
  readouts use the `fitted` interface; probability-only entries use `native`. A prior cell retains
  its own probability interface even when that model also provides embeddings.
- Each measurement links to its source with `sourceId`; its original value is
  in `sourceValue`. Intervals retain their sampling unit. An unrun endpoint has
  `value: null` and an explanatory note. Evaluated community cells carry
  `verification.status`: `contributor_evaluated`, `reproduced_by_bend`, or
  `pending_review` in previews. `verification.reviewPath` links to the receipt.
  Reproduced cells also contain the rerun metric, reviewer, notes and evidence.
  The CSV export includes the per-task verification status.
- Its source includes the evidence download `url`, `sha256`, `runIdentity`,
  `protocolVersion`, `submissionPath` and `reviewPath`.

Show a community label and these source links in model/result details. Do not
label a community result as "Manuscript Table 1" or link it to the paper's source
CSV. Keep the existing fixed-reference scoring logic. The frontend must escape
model names and other contributor text as it does existing data.

`submissionPath` is repository-relative; link it to the repository publication
branch or copy those files into the static build. The evidence `url` is
a direct external link. The snapshot's `counts` describe paper data;
derive current displayed model counts from the combined arrays.

## Publication and review

Deploy from the publication branch after maintainer review. PR builds use
preview mode; push builds require matching review records. Maintainers rescore
the evidence before merging, following the [review procedure](../docs/reviewing.md).
Configure branch protection to require their approval.

Deployment is not configured in this repository. Connect the static build to
the hosting service when deploying. Submitted adapters must not run during
site builds or privileged PR checks.

## Snapshot provenance

`snapshot.json` records the hashes of the files imported from the website
repository. The paper data came from:

- Repository: `genomic-bending-leaderboard`
- Producing commit: `509a14056b6102258a2df1c83eefe0ee76140e32`
- Path: `data/benchmark.json`
- Manuscript revision recorded inside the snapshot:
  `1abee7c638616c578b2fea497e63b59e68752c01`

Changes to the paper results require a separate scientific revision.
