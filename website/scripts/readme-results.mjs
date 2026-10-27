import fs from "node:fs/promises";
import { finite, indexData, ordered, overallScore, ranks, scoreCoverage } from "../src/scoring.js";

const root = new URL("../../", import.meta.url);
const data = JSON.parse(await fs.readFile(new URL("website/data/benchmark.json", root), "utf8"));
const lookup = indexData(data);
const models = ordered(data.models.filter(m => m.kind === "foundation"), m => overallScore(data, m.id));
const ranking = ranks(models, m => overallScore(data, m.id));
const headings = {
  prior: ["Hidden-base", "loss", "bits ↓"],
  opensplice: ["Splicing", "effects", "Spearman ↑"],
  context: ["Cell", "contrast", "Spearman ↑"],
  tissue_identification: ["Tissue", "identification", "top-1 % ↑"],
  background: ["Background", "interaction", "Spearman ↑"],
  repair_percentile: ["Single-edit", "rank", "percentile ↓"],
  cell_selective: ["Cell", "selectivity", "log₂ utility ↑"],
  atlas_profile: ["Multi-cell", "gain", "log₂ gain ↑"],
};
const groups = ["Prior", "Function", "Context", "Interactions", "Design"];
const escape = value => String(value).replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c]));
const keepTogether = value => escape(value).replaceAll(" ", "&nbsp;");
const title = model => model.label.replace(" · native", "");
const readout = model => model.interface === "native" ? "Native outputs" : "Fitted readouts";
const cell = (model, task) => lookup.measurements.get(`${model.id}:${task.id}`);
const display = measurement => finite(measurement?.value) ? measurement.displayValue : "—";
const partial = model => scoreCoverage(data, model.id).tasks.complete < data.tasks.length;
const score = model => finite(overallScore(data, model.id)) ? overallScore(data, model.id).toFixed(1) : "—";
const maxScore = Math.max(100, ...models.map(m => overallScore(data, m.id)).filter(finite));

function tint(task, value) {
  const values = models.map(m => cell(m, task)?.value).filter(finite);
  const lo = Math.min(task.baseline.value, ...values), hi = Math.max(task.baseline.value, ...values);
  const fraction = hi === lo ? .5 : task.direction === "higher" ? (value - lo) / (hi - lo) : (hi - value) / (hi - lo);
  return .025 + .16 * Math.pow(Math.max(0, Math.min(1, fraction)), 1.6);
}

function figure(dark) {
  const width = 1200, modelWidth = 228, scoreWidth = 92, columnWidth = 110;
  const top = 108, rowHeight = 48, referenceY = top + models.length * rowHeight + 16;
  const height = referenceY + 56;
  const ink = dark ? "#e6edf3" : "#283b36", muted = dark ? "#9ba9b2" : "#61736c";
  const rule = dark ? "#303c42" : "#d8dfda", paper = dark ? "#0d1117" : "#ffffff";
  const colors = dark ? ["#d6b063", "#8eb9e6", "#83cbb7", "#b6a0d5", "#e3a08d"] : data.categories.map(c => c.color);
  const color = task => colors[data.categories.findIndex(c => c.id === task.categoryId)];
  const out = [`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="title desc">
<title id="title">BEND 2.0 benchmark results</title>
<desc id="desc">${models.length} model and readout configurations, ordered by the website's combined score, with all ${data.tasks.length} task measurements and a separate experimental reference. Daggers mark incomplete coverage. A text version follows the figure in the README.</desc>
<style>text{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;fill:${ink};font-variant-numeric:tabular-nums}.muted{fill:${muted}}.name{font-size:18px;font-weight:500}.value{font-size:18px}.label{font-size:16px}.small{font-size:14px}</style>
<rect width="${width}" height="${height}" fill="${paper}"/>`];
  const text = (x, y, value, cls = "label", anchor = "start", fill = "") => out.push(`<text x="${x}" y="${y}" class="${cls}" text-anchor="${anchor}"${fill ? ` style="fill:${fill}"` : ""}>${escape(value)}</text>`);
  const line = (x1, y, x2, stroke = rule, weight = 1) => out.push(`<path d="M${x1} ${y}H${x2}" stroke="${stroke}" stroke-width="${weight}"/>`);
  line(0, 1, width);
  text(32, 83, "Model / readout", "label muted");
  const scoreX = modelWidth + scoreWidth / 2;
  text(scoreX, 26, "Overall", "small muted", "middle");
  text(scoreX, 57, "Combined", "label", "middle");
  text(scoreX, 77, "score ↑", "label", "middle");
  let start = 0;
  data.categories.forEach((category, i) => {
    const count = data.tasks.filter(t => t.categoryId === category.id).length;
    const left = modelWidth + scoreWidth + start * columnWidth;
    line(left + 3, 1, left + count * columnWidth - 3, colors[i], 2);
    text(left + count * columnWidth / 2, 26, groups[i], "small", "middle", colors[i]);
    start += count;
  });
  data.tasks.forEach((task, i) => {
    const x = modelWidth + scoreWidth + (i + .5) * columnWidth;
    headings[task.id].forEach((label, j) => text(x, [55, 75, 96][j], label, j === 2 ? "small muted" : "label", "middle"));
  });
  line(0, top, width);
  function metrics(row, y) {
    data.tasks.forEach((task, i) => {
      const measurement = row(task), x = modelWidth + scoreWidth + i * columnWidth;
      if (finite(measurement?.value)) out.push(`<rect x="${x + 3}" y="${y + 5}" width="${columnWidth - 6}" height="${rowHeight - 10}" fill="${color(task)}" opacity="${tint(task, measurement.value).toFixed(4)}"/>`);
      text(x + columnWidth / 2, y + 30, display(measurement), `value${finite(measurement?.value) ? "" : " muted"}`, "middle");
    });
  }
  models.forEach((model, i) => {
    const y = top + i * rowHeight;
    text(15, y + 29, ranking.get(model.id) || "—", "small muted", "middle");
    text(32, y + 21, title(model), "name");
    text(32, y + 39, readout(model), "small muted");
    text(scoreX, y + 28, score(model), "value", "middle");
    if (partial(model)) text(scoreX + (score(model).length * 5.1) + 4, y + 20, "†", "small muted");
    if (finite(overallScore(data, model.id))) line(modelWidth + 13, y + 38, modelWidth + 13 + Math.max(0, overallScore(data, model.id)) / maxScore * (scoreWidth - 26), muted, 1.5);
    metrics(task => cell(model, task), y);
    line(0, y + rowHeight, width);
  });
  line(0, referenceY, width);
  text(32, referenceY + 29, "Experimental reference", "label");
  text(scoreX, referenceY + 30, "—", "value muted", "middle");
  metrics(task => data.references.find(r => r.taskId === task.id), referenceY);
  line(0, referenceY + rowHeight, width);
  return out.join("\n") + "\n</svg>\n";
}

const nativeTable = [
  `| Model / readout | Combined<br>score ↑ | ${data.tasks.map(t => headings[t.id].map(keepTogether).join("<br>")).join(" | ")} |`,
  `| :--- | ---: | ${data.tasks.map(() => "---:").join(" | ")} |`,
  ...models.map(m => `| ${keepTogether(title(m))}<br><sub>${keepTogether(readout(m))}</sub> | ${score(m)}${partial(m) ? "†" : ""} | ${data.tasks.map(t => display(cell(m, t))).join(" | ")} |`),
  `| Experimental&nbsp;reference | — | ${data.tasks.map(t => display(data.references.find(r => r.taskId === t.id))).join(" | ")} |`,
].join("\n");
const section = `<!-- BEGIN GENERATED RESULTS: node website/scripts/readme-results.mjs -->
## Benchmark results

<a href="docs/assets/results-light.svg">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/results-dark.svg">
    <img src="docs/assets/results-light.svg" alt="BEND 2.0 results for ${data.tasks.length} tasks and ${models.length} model/readout configurations, ordered by combined score. Full values are available in the text table below.">
  </picture>
</a>

Combined scores use **NTv3 650M post = 100** and weight available categories
equally. † Incomplete task coverage; missing results are omitted. This is the
website’s summary score, not a manuscript metric.

<details>
<summary>Results as a text table</summary>

${nativeTable}

On functional tasks, fitted readouts use frozen embeddings. Native outputs use the model's released
predictions, with task-specific calibration; multi-cell design fits a head to
those outputs. Experimental references are comparisons, not ceilings.
See [task definitions](docs/tasks.md) and the
[source measurements](website/data/benchmark.json) for protocols and uncertainty.

</details>
<!-- END GENERATED RESULTS -->`;
for (const theme of ["light", "dark"]) await fs.writeFile(new URL(`docs/assets/results-${theme}.svg`, root), figure(theme === "dark"));
const readmeURL = new URL("README.md", root);
const readme = await fs.readFile(readmeURL, "utf8");
const marker = /<!-- BEGIN GENERATED RESULTS:[\s\S]*?<!-- END GENERATED RESULTS -->/;
const updated = marker.test(readme) ? readme.replace(marker, section) : readme.replace("## Evaluate your model", `${section}\n\n## Evaluate your model`);
await fs.writeFile(readmeURL, updated);
console.log(`Updated README results: ${models.length} model/readout rows, ${data.tasks.length} tasks, light and dark artwork.`);
