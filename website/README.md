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
the development server after changing contribution JSON files. Set the paper
link in `index.html` when the publication URL is available.

## Leaderboard data

The build reads:

- `data/benchmark.paper.json`: the paper results.
- `../submissions/*.json`: community submissions.
- `../reviews/*.json`: matching rescoring and reproduction records.

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

## Publication and review

Deploy from the publication branch after the
[maintainer review](../docs/reviewing.md). PR builds use preview mode; push
builds require matching review records.

Deployment is not configured. Connect `website/dist/` to the hosting service
when deploying. Import provenance is recorded in [snapshot.json](snapshot.json).
