import { finite } from "./scoring.js";
import { chartDomain } from "./results-chart.js";

const escape = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        character
      ],
  );
const format = (value, precision) => value.toFixed(precision).replace("-", "−");

const referenceLabels = {
  opensplice: "Agreement between RNA measurements",
  context: "Agreement between repeat subsets",
  tissue_identification: "Identification across donor halves",
  background: "Agreement across cell types",
  repair_percentile: "Selection across repeat subsets",
  cell_selective: "Selection across RNA repeat subsets",
  atlas_profile: "Selection across RNA measurements",
};

function readoutLabel(model, taskId) {
  if (taskId === "prior")
    return model.kind === "foundation" ? "Sequence probabilities" : "Sequence baseline";
  if (model.interface === "native")
    return taskId === "atlas_profile" ? "Head fitted to native outputs" : "Native outputs";
  if (model.interface === "fitted")
    return model.kind === "foundation" ? "Embedding-fitted head" : "Fitted sequence features";
  return model.interface === "sequence" ? "Sequence baseline" : "Task-trained model";
}

/** Prepare plotted records without changing scores, uncertainty, or the source roster. */
export function explorerRows(
  data,
  taskId,
  { readout = "all", showReferences = true, showBaselines = false } = {},
) {
  const task = data.tasks.find((entry) => entry.id === taskId);
  if (!task) throw new RangeError(`Unknown benchmark task: ${taskId}`);
  const category = data.categories.find((entry) => entry.id === task.categoryId);
  const measurements = new Map(
    data.measurements
      .filter((cell) => cell.taskId === taskId)
      .map((cell) => [cell.modelId, cell]),
  );
  const repeatRecords = new Map(
    (data.supplementary?.multiCellRepeats?.points || []).map((point) => [point.modelId, point]),
  );
  // A readout filter describes foundation-model interfaces; baseline models retain
  // their own labels and can be shown independently for a useful comparison.
  const models = data.models.filter((model) =>
    model.kind === "foundation"
      ? readout === "all" || model.interface === readout
      : showBaselines,
  );
  const omitted = models.filter((model) => !finite(measurements.get(model.id)?.value));
  const rows = models
    .filter((model) => finite(measurements.get(model.id)?.value))
    .map((model) => ({
      id: model.id,
      model,
      cell: measurements.get(model.id),
      kind: model.kind === "foundation" ? "model" : "baseline",
      name: model.label.replace(" · native", ""),
      subtitle: readoutLabel(model, taskId),
      repeats: taskId === "atlas_profile" ? repeatRecords.get(model.id)?.repeatValues || [] : [],
    }));
  const reference = data.references.find((entry) => entry.taskId === taskId);
  if (showReferences && finite(reference?.value)) {
    rows.push({
      id: reference.modelId || "experimental_reference",
      model: null,
      cell: reference,
      kind: "reference",
      name: taskId === "background" ? "HepG2–K562 transfer" : "Experimental reference",
      subtitle: referenceLabels[taskId] || "Experimental measurements",
      repeats: taskId === "atlas_profile"
        ? repeatRecords.get("experimental_reference")?.repeatValues || []
        : [],
    });
  }
  rows.sort((a, b) =>
    (a.cell.value - b.cell.value) * (task.direction === "lower" ? 1 : -1),
  );
  const values = rows.flatMap(({ cell, repeats }) => [
    cell.value, cell.uncertainty?.low, cell.uncertainty?.high, ...repeats,
  ]);
  // Tiny negative bootstrap bounds should not add a whole negative tick to
  // these correlation plots. Only the viewport changes; records stay intact.
  const startsAtZero = taskId === "context" || taskId === "background";
  // A tighter multi-cell viewport fits both RNA measurements and the reference.
  // Retain automatic bounds if a future observation or interval extends beyond it.
  const compactMultiCell = taskId === "atlas_profile" &&
    values.every(value => !finite(value) || (value >= -.75 && value <= 1.75));
  const domain = compactMultiCell
    ? { min: -.75, max: 1.75, ticks: [-.5, 0, .5, 1, 1.5] }
    : chartDomain(startsAtZero ? values.map(value => finite(value) ? Math.max(0, value) : value) : values);
  return { task, category, rows, omitted, domain };
}

function tickPrecision(ticks) {
  const step = ticks[1] - ticks[0];
  let precision = 0;
  while (precision < 6 && Math.abs(step * 10 ** precision - Math.round(step * 10 ** precision)) > 1e-8)
    precision++;
  return precision;
}

/** Responsive HTML/SVG chart. Existing data-cell and data-reference handlers open details. */
export function taskExplorerChart(data, taskId, options = {}) {
  const { task, category, rows, domain } = explorerRows(data, taskId, options);
  const selected = options.selected || [];
  if (!rows.some((row) => row.model))
    return '<p class="explorer-empty">No model results for this readout. Choose another readout to compare models.</p>';
  const color = category?.color || "#315a49";
  const percent = (value) => 100 * (value - domain.min) / (domain.max - domain.min);
  const position = (value) => `${percent(value).toFixed(5)}%`;
  const grid = domain.ticks.map((tick) =>
    `<line class="explorer-grid${Math.abs(tick) < 1e-8 ? " zero" : ""}" x1="${position(tick)}" x2="${position(tick)}" y1="0" y2="30"/>`,
  ).join("");
  const digits = tickPrecision(domain.ticks);
  const ticks = domain.ticks.map((tick) =>
    `<span style="left:${position(tick)}">${format(tick, digits)}</span>`,
  ).join("");

  const rowMarkup = rows.map(({ id, model, cell, kind, name, subtitle, repeats }) => {
    const action = kind === "reference"
      ? `data-reference="${escape(taskId)}"`
      : `data-cell="${escape(id)}:${escape(taskId)}"`;
    const interval = cell.uncertainty;
    const details = interval
      ? `; 95% interval ${format(interval.low, task.precision)} to ${format(interval.high, task.precision)}`
      : repeats.length
        ? `; RNA measurements ${repeats.map((value) => format(value, task.precision)).join(" and ")}`
        : "";
    const label = `${name}, ${subtitle}: ${cell.displayValue}${details}`;
    const start = percent(Math.max(domain.min, Math.min(0, cell.value)));
    const width = Math.max(0, percent(Math.min(domain.max, Math.max(0, cell.value))) - start);
    let uncertainty = "";
    if (interval && interval.high >= domain.min && interval.low <= domain.max) {
      const caps = [interval.low, interval.high]
        .filter(value => value >= domain.min && value <= domain.max)
        .map(value => `<line x1="${position(value)}" x2="${position(value)}" y1="11" y2="19"/>`).join("");
      uncertainty = `<g class="explorer-interval"><line x1="${position(Math.max(domain.min, interval.low))}" x2="${position(Math.min(domain.max, interval.high))}" y1="15" y2="15"/>${caps}</g>`;
    }
    const markers = repeats.length
      ? repeats.map((value, index) => `<circle class="explorer-point repeat repeat-${index}" cx="${position(value)}" cy="15" r="3.3"/>`).join("")
      : cell.value < domain.min
        ? '<path class="explorer-point off-scale" d="M 5 11 L 1 15 L 5 19" style="fill:none"/>'
        : `<circle class="explorer-point${taskId === "atlas_profile" ? " mean-only" : ""}" cx="${position(cell.value)}" cy="15" r="3.3"/>`;
    return `<button type="button" class="explorer-row ${kind}${model?.interface === "native" ? " native" : ""}${selected.includes(id) ? " selected" : ""}" ${action} data-explorer-row="${escape(id)}" data-value="${cell.value}" aria-label="${escape(label)}" style="--row-color:${kind === "model" ? color : "#99978f"}"><span class="explorer-model"><span>${escape(name)}</span><small>${escape(subtitle)}</small></span><svg class="explorer-track" width="100%" height="30" aria-hidden="true"><g>${grid}</g><rect class="explorer-bar" x="${start.toFixed(5)}%" y="9" width="${width.toFixed(5)}%" height="12" rx="2"/>${uncertainty}${markers}</svg><span class="explorer-value">${escape(cell.displayValue)}</span></button>`;
  }).join("");

  return `<div class="explorer-chart" style="--category:${color}" role="group" aria-label="${escape(task.label)}; ${task.direction === "lower" ? "lower" : "higher"} is better"><div class="explorer-axis" aria-hidden="true"><span></span><div>${ticks}</div><span></span></div>${rowMarkup}<div class="explorer-axis bottom" aria-hidden="true"><span></span><div>${ticks}</div><span></span></div></div>`;
}
