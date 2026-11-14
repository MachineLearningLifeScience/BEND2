# README figures

The results graphics are vector SVGs with light and dark variants. They read the
reference scores from `data/benchmark.paper.json`; no model inference or network
access is needed to redraw them.

From the repository root, with Node.js installed:

```bash
node docs/figures/build_results.mjs
```

This updates both SVGs and the corresponding text table in the README. The
combined score follows the [reference-index definition](../../data/sources.md#reference-index-audit).
The capability diagrams and banner are static assets in `docs/assets/`.
