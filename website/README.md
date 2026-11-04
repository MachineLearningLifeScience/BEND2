# Website

## Run locally

From the repository root, with the benchmark environment activated:

```bash
pip install -e .
npm --prefix website ci
npm --prefix website run dev
```

To build the static site:

```bash
npm --prefix website run build
```

The output is `website/dist/`. Both commands first generate leaderboard data.
Node.js 22 or newer is required. If Python is elsewhere, set
`BEND2_PYTHON=/absolute/path/to/venv/bin/python` before the npm command. Restart
the development server after changing contribution JSON files.

## Leaderboard data

The public [BEND 2.0 data release on Hugging Face](https://huggingface.co/datasets/yhsure/BEND2)
provides the evaluation data. It is linked under Code & data, separately from
the downloadable results; original dataset links remain under Data sources.

The build reads:

- `data/benchmark.paper.json`: the archived paper results and documented additions.
- `../submissions/*.json`: community submissions.
- `../reviews/*.json`: matching rescoring and reproduction records.

`data/evaluation-updates.json` is the audit record published alongside the site.
Its additions are already applied to `benchmark.paper.json`; the website build
does not apply that record again.

The two native NTv3 rows share their parent checkpoints’ sequence-prior evaluations,
using the same recorded estimates and intervals. The archived manuscript table is
unchanged; the additions and diagnostic sources are documented separately.
The completed CENO OpenSplice evaluation is included with its source record and
gene-bootstrap interval in `provenance/coverage-20261027/ceno-opensplice/`.
The completed Evo2 tissue-identification evaluation identifies 11 of 51 tissues
(21.6%) over 5,782 held-out genes. Its native-FP8 extraction, independent audit,
source records and checksums are archived in `provenance/evo2-tissue-20261102/`.
Tissue-identification intervals remain omitted across all models; the returned
Evo2 bounds are retained as provenance. Evo2 now has all eight task values.

The generated `data/benchmark.json` combines these inputs; always rebuild from
`benchmark.paper.json`. Every published submission must have a matching review.
For PR previews, set `BEND2_PREVIEW_SUBMISSIONS=1`; all community results are
then labelled **Awaiting review**, including those with proposed receipts.

## README results

After rebuilding the reviewed leaderboard data, refresh the README table with:

```bash
node website/scripts/readme-results.mjs
```

Run this from the repository root. It updates the light and dark figures and
the text table from the same measurements and scoring code used by the website.
Cell shading runs from each task's fixed baseline to its best model result;
worse-than-baseline values remain neutral and do not stretch the colour scale.

## Publication and review

Deploy from the publication branch after the
[maintainer review](../docs/reviewing.md). PR builds use preview mode; push
builds require matching review records.

The **Deploy GitHub Pages** workflow builds and deploys `website/dist/` on pushes
to `main` and when manually requested. Enable Pages with **GitHub Actions** as
its source.
Repository visibility and organization settings determine when Pages can be
enabled. See [release setup](../docs/releasing.md). Import provenance is recorded
in [snapshot.json](snapshot.json).

The imported runtime includes the current navigation, design walkthrough, score
breakdowns and social preview. `snapshot.json` records its source revision and
original hashes; submission review, model evidence and verification fields remain
part of this repository’s integration. Set `SITE_URL` to the full public site URL
when building for a host that needs absolute social-image and canonical URLs.
