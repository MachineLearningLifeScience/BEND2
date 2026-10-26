# Website

This folder contains a committed starting snapshot of the BEND 2.0 website,
connected to the benchmark's contribution flow. It preserves the existing
visual design and scoring. The separate active website project remains the
authoritative place for its ongoing design work until those changes are
integrated deliberately; its unfinished edits were not copied or modified.

## Run locally

From the repository root, with the benchmark environment activated:

```bash
pip install -e .
npm --prefix website ci
npm --prefix website run dev
```

Open the printed local URL. For a self-contained static output:

```bash
npm --prefix website run build
```

The output is `website/dist/`. Both commands first generate leaderboard data.
Node.js 22 or newer is required. If the active Python is elsewhere, set
`BEND2_PYTHON=/absolute/path/to/venv/bin/python` before the npm command. Restart
the development server after changing contribution JSON files. The committed
snapshot still has a placeholder paper link; set the verified publication URL
when that release information is available.

## Website data integration

The leaderboard is built from three reviewable inputs:

- `data/benchmark.paper.json`: the frozen paper snapshot.
- `../submissions/*.json`: community contributions accepted by maintainer review
  and merge into the publication branch.
- `../reviews/*.json`: matching trusted rescoring receipts and any per-task rerun records.

Generate the frontend's combined `data/benchmark.json`:

```bash
python website/scripts/build_leaderboard.py
```

Run this after installing the repository package (`pip install -e .`) and before
the website's static build. The same builder is available as
`bend2.submissions.build_leaderboard` for other build systems. Arguments
`--reference`, `--submissions`, `--reviews` and `--output` support separate
folders. Publication requires every contribution to have a valid matching review.
Use `--preview` (or `BEND2_PREVIEW_SUBMISSIONS=1` with npm) only for PR previews;
all community rows and task details are explicitly labelled **Awaiting review**
in preview mode, even when the PR includes a proposed receipt. The builder does not download evidence or run model code.

The output adds community models, eight task cells per model and evidence
sources. Missing tasks stay missing. It preserves all paper models,
measurements, references and normalization anchors. For consistency with the
site's existing rank contract, community `value` and `displayValue` use each
task's stated display precision; `sourceValue` and the submission retain the
exact result. Build from the paper snapshot each time, not a previous combined
file. An empty submissions directory reproduces the paper data unchanged.

## Frontend contract

The current website already consumes the `models`, `measurements`, and `sources`
arrays in `data/benchmark.json`. Community records extend that shape:

- A model has `origin: "community"`, a public `url`, `submissionPath`, and its
  evaluated model `declarations`. Its model kind is `foundation`, so it belongs
  with models rather than scientific baselines. Embedding readouts use the
  `fitted` interface; probability-only entries use `native`. A prior cell retains
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
branch or copy those compact files into the static build. The evidence `url` is
a direct external link. The frozen snapshot's `counts` describe paper data;
derive current displayed model counts from the combined arrays.

## Publication and review

Only the publication branch should deploy the public site. A pull request can
build a preview with its candidate contribution, but a preview is not an
accepted public leaderboard result. Require maintainer review for contribution
PRs and verify their downloaded evidence before merging; see
[the maintainer procedure](../docs/reviewing.md).

PR CI enables preview mode; push builds require matching receipts. Neither
performs the actual trusted rescoring. Maintainers do that before acceptance.
Receipt JSON is not authentication: require protected-branch review before
publishing it. A contributor can create JSON fields but cannot self-grant a
public status merely by submitting them.

No deployment workflow is assumed or installed here. Connect this build step to
the website's chosen static hosting workflow when that deployment is configured.
Do not execute a submitted adapter during a site build or privileged PR check.

## Snapshot provenance

The runtime files and paper snapshot were copied from the committed website source.
`snapshot.json` records the imported file hashes before integration edits. The
paper data itself was copied byte-for-byte:

- Repository: `genomic-bending-leaderboard`
- Producing commit: `509a14056b6102258a2df1c83eefe0ee76140e32`
- Path: `data/benchmark.json`
- Manuscript revision recorded inside the snapshot:
  `1abee7c638616c578b2fea497e63b59e68752c01`

The separate website checkout also had unfinished visual edits. This integration
uses its committed benchmark data and does not copy or modify those edits.
Changes to the frozen paper snapshot need an explicit scientific update, rather
than being a side effect of a community model submission.
