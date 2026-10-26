import { finite, overallScore } from "./scoring.js";

const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const format = (x, digits = 2) => x.toFixed(digits).replace("-", "−");

export function chartDomain(values, intervals = 4, includeZero = true) {
  const numbers = values.filter(finite);
  if (includeZero || !numbers.length) numbers.push(0);
  const lo = Math.min(...numbers),
    hi = Math.max(...numbers);
  const span = hi - lo || 1,
    rough = span / intervals,
    power = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((n) => n * power).find((n) => n >= rough);
  const min = Math.floor(lo / step) * step,
    max = hi === lo ? min + 1 : Math.ceil(hi / step) * step;
  const ticks = [];
  for (let n = min; n <= max + step / 100; n += step)
    ticks.push(Math.abs(n) < step / 100 ? 0 : n);
  return { min, max, ticks };
}

export function resultsChart(
  data,
  { taskId, models, selected = [], showBaselines = false },
) {
  const task = data.tasks.find((t) => t.id === taskId),
    isIndex = !task;
  const category = data.categories.find((c) => c.id === task?.categoryId);
  const color = category?.color || "#315a49";
  const records = new Map(
    data.measurements.map((m) => [`${m.modelId}:${m.taskId}`, m]),
  );
  const entries = models
    .filter((m) => showBaselines || m.kind === "foundation")
    .map((m) => ({
      model: m,
      kind: m.kind === "foundation" ? "model" : "baseline",
      cell: isIndex
        ? {
            value: overallScore(data, m.id),
            displayValue: finite(overallScore(data, m.id))
              ? format(overallScore(data, m.id), 1)
              : "—",
          }
        : records.get(`${m.id}:${taskId}`),
    }));
  const reference = data.references.find((r) => r.taskId === taskId);
  if (reference)
    entries.push({ model: null, cell: reference, kind: "reference" });
  const omitted = entries
    .filter((e) => !finite(e.cell?.value))
    .map((e) => e.model?.label);
  const rows = entries
    .filter((e) => finite(e.cell?.value))
    .sort(
      (a, b) =>
        (a.cell.value - b.cell.value) * (task?.direction === "lower" ? 1 : -1),
    );
  if (!rows.some((row) => row.model))
    return '<div class="empty-chart"><p>No measurements for these filters.</p><button class="text-action" data-action="reset-filters">Clear search and filters</button></div>';
  const repeats = data.supplementary?.multiCellRepeats?.points || [];
  const domain = chartDomain(
    rows.flatMap((r) => [
      r.cell.value,
      r.cell.uncertainty?.low,
      r.cell.uncertainty?.high,
      ...(taskId === "atlas_profile"
        ? repeats.find(
            (p) => p.modelId === (r.model?.id || "experimental_reference"),
          )?.repeatValues || []
        : []),
    ]),
  );
  const pct = (v) => ((v - domain.min) / (domain.max - domain.min)) * 100;
  const step = domain.ticks[1] - domain.ticks[0];
  let tickDigits = 0;
  while (
    tickDigits < 6 &&
    Math.abs(step * 10 ** tickDigits - Math.round(step * 10 ** tickDigits)) >
      1e-8
  )
    tickDigits++;
  const ticks = domain.ticks
    .map((t) => `<span style="left:${pct(t)}%">${format(t, tickDigits)}</span>`)
    .join("");
  const grid = domain.ticks
    .map(
      (t) =>
        `<i class="result-gridline ${Math.abs(t) < 1e-8 ? "zero" : ""}" style="left:${pct(t)}%"></i>`,
    )
    .join("");
  const axisLabels = {
    prior: "Hidden-base loss · bits",
    opensplice: "Macro-gene Spearman ρ",
    context: "Macro-element Spearman ρ",
    tissue_identification: "Correct tissue · %",
    background: "Macro-element Spearman ρ",
    repair_percentile: "Measured residual rank · percentile",
    cell_selective: "Selection utility · log₂",
    atlas_profile: "Gain over random · log₂",
  };
  const label = isIndex ? "Reference index" : axisLabels[taskId];
  let html = `<div class="results-plot" style="--category:${color}"><div class="plot-column-labels"><span>Model / readout</span><span>${esc(label)} ${task?.direction === "lower" ? "↓" : "↑"}</span><span>Result</span></div><div class="result-axis"><div></div><div>${ticks}</div><div></div></div>`;
  html += rows
    .map(({ model, cell, kind }) => {
      const id = model?.id || "experimental_reference",
        isRef = kind === "reference";
      const name = isRef
        ? taskId === "background"
          ? "HepG2–K562 transfer"
          : "Experimental reference"
        : model.label.replace(" · native", "");
      const referenceLabels = {
        opensplice: "Agreement between RNA measurements",
        context: "Repeat-subset contrast agreement",
        tissue_identification: "Identification across donor halves",
        background: "Agreement across cell types",
        repair_percentile: "Selection across repeat subsets",
        cell_selective: "Selection across RNA repeat subsets",
        atlas_profile: "Selection across RNA measurements",
      };
      let subtitle = isRef
        ? referenceLabels[taskId]
        : model.interface === "native"
          ? taskId === "atlas_profile"
            ? "Head fitted to native outputs"
            : "Native outputs"
          : model.interface === "fitted"
            ? taskId === "prior"
              ? "Sequence probabilities"
              : "Embedding-fitted head"
            : model.interface === "sequence"
              ? "Sequence baseline"
              : "Task-trained model";
      const action = isRef
        ? `data-reference="${taskId}"`
        : isIndex
          ? `data-model="${id}"`
          : `data-cell="${id}:${taskId}"`;
      const uncertainty = cell.uncertainty;
      const rep =
        taskId === "atlas_profile"
          ? repeats.find((p) => p.modelId === id)
          : null;
      const details = uncertainty
        ? ` · 95% interval ${format(uncertainty.low, task.precision)} to ${format(uncertainty.high, task.precision)}`
        : "";
      return `<div class="result-row ${kind} ${selected.includes(id) ? "selected" : ""}" data-result-row="${id}"><div class="result-model">${!isRef ? `<input type="checkbox" data-select="${id}" aria-label="Compare ${esc(model.label)}" ${selected.includes(id) ? "checked" : ""} ${selected.length === 3 && !selected.includes(id) ? "disabled" : ""}>` : '<span class="reference-indent"></span>'}<button ${isRef ? action : `data-model="${id}"`}><span>${esc(name)}</span><small>${esc(subtitle)}</small></button></div><button class="result-track" ${action} aria-label="${esc(name)}: ${esc(cell.displayValue)}${esc(details)}" title="${esc(name)}: ${esc(cell.displayValue)}${esc(details)}">${grid}${uncertainty ? `<span class="result-interval" style="left:${pct(uncertainty.low)}%;width:${pct(uncertainty.high) - pct(uncertainty.low)}%"></span>` : ""}${rep ? rep.repeatValues.map((v, i) => `<i class="result-point repeat-point repeat-point-${i}" style="left:${pct(v)}%"></i>`).join("") : `<i class="result-point ${taskId === "atlas_profile" ? "mean-point" : model?.interface === "native" ? "native-point" : ""}" style="left:${pct(cell.value)}%"></i>`}</button><button class="result-number" ${action}>${esc(cell.displayValue)}</button></div>`;
    })
    .join("");
  html += `<div class="result-axis bottom"><div></div><div>${ticks}</div><div></div></div></div><div class="plot-footnote"><span>${isIndex ? "Fixed reference: NTv3 650M post = 100. Available tasks and categories are averaged." : taskId === "atlas_profile" ? '<i class="legend-point"></i> RNA measurement 1 <i class="legend-point open"></i> RNA measurement 2 <i class="legend-point mean"></i> Mean only' : "Points show estimates; whiskers show reported 95% intervals."}</span><button class="text-action" ${isIndex ? 'data-action="method"' : `data-task="${taskId}"`}>${isIndex ? "Score definition" : "Task & measurement details"} ↗</button></div>`;
  if (omitted.length)
    html += `<p class="chart-missing">${isIndex ? "No downstream results" : "No result in this snapshot"}: ${omitted.map(esc).join(", ")}.</p>`;
  return html;
}
