import { finite } from "./scoring.js";
import { chartDomain } from "./results-chart.js";

const escape = (value) => String(value ?? "").replace(
  /[&<>"']/g,
  (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character],
);

const comparisons = {
  training: [
    { id: "ntv3_100m", label: "NTv3 100M", first: "ntv3_100m_pre", second: "ntv3_100m_post" },
    { id: "ntv3_650m", label: "NTv3 650M", first: "ntv3_650m_pre", second: "ntv3_650m_post" },
  ],
  readout: [
    { id: "alphagenome", label: "AlphaGenome", first: "alphagenome", second: "alphagenome_fitted" },
    { id: "ntv3_100m", label: "NTv3 100M post", first: "ntv3_100m_native", second: "ntv3_100m_post" },
    { id: "ntv3_650m", label: "NTv3 650M post", first: "ntv3_650m_native", second: "ntv3_650m_post" },
  ],
};

const axisLabels = {
  prior: "Hidden-base loss · bits/base",
  opensplice: "Macro-gene Spearman ρ",
  context: "Macro-element Spearman ρ",
  tissue_identification: "Correct tissue · %",
  background: "Macro-element Spearman ρ",
  repair_percentile: "Measured residual rank · percentile",
  cell_selective: "Selection utility · log₂",
  atlas_profile: "Gain over random · log₂",
};

/** Matched measurements only: never substitute a different task or model. */
export function pairedData(data, taskId, mode = "training") {
  const task = data.tasks.find((item) => item.id === taskId);
  const models = new Map(data.models.map((model) => [model.id, model]));
  const measurements = new Map(data.measurements.map((cell) => [`${cell.modelId}:${cell.taskId}`, cell]));
  const definitions = comparisons[mode] || [];
  const labels = mode === "training"
    ? ["Sequence pretraining", "Functional post-training"]
    : taskId === "atlas_profile"
      ? ["Head on native outputs", "Head on embeddings"]
      : ["Native outputs", "Embedding-fitted head"];
  const pairs = [], omitted = [];

  for (const definition of definitions) {
    const first = { model: models.get(definition.first), cell: measurements.get(`${definition.first}:${taskId}`) };
    const second = { model: models.get(definition.second), cell: measurements.get(`${definition.second}:${taskId}`) };
    if (task && first.model && second.model && finite(first.cell?.value) && finite(second.cell?.value)) {
      pairs.push({ id: definition.id, label: definition.label, first, second });
    } else {
      omitted.push(definition.label);
    }
  }

  return {
    task,
    mode,
    labels,
    pairs,
    omitted,
    domain: chartDomain(pairs.flatMap(({ first, second }) => [first.cell.value, second.cell.value])),
    color: data.categories.find((category) => category.id === task?.categoryId)?.color || "#315a49",
  };
}

export function pairedChart(data, taskId, mode = "training") {
  const { task, pairs, omitted, labels, domain, color } = pairedData(data, taskId, mode);
  if (!task) return '<p class="paired-empty">Choose a task to compare.</p>';
  if (!pairs.length) return `<p class="paired-empty">No paired ${mode === "training" ? "training" : "readout"} results are available for ${escape(task.label.toLowerCase())}.</p>`;

  const position = (value) => 100 * (value - domain.min) / (domain.max - domain.min);
  const formatTick = (value) => String(Number(value.toFixed(6))).replace("-", "−");
  const ticks = domain.ticks.map((value) => `<span style="left:${position(value)}%">${formatTick(value)}</span>`).join("");
  const grid = domain.ticks.map((value) => `<i class="paired-gridline${value === 0 ? " zero" : ""}" style="left:${position(value)}%"></i>`).join("");
  const direction = task.direction === "lower" ? "← Lower is better" : "Higher is better →";
  const rows = pairs.map(({ id, label, first, second }) => {
    const left = Math.min(position(first.cell.value), position(second.cell.value));
    const width = Math.abs(position(second.cell.value) - position(first.cell.value));
    const values = [first, second].map(({ model, cell }, index) => {
      const value = cell.displayValue || cell.value.toFixed(task.precision);
      return `<button class="paired-value ${index ? "second" : "first"}" data-cell="${escape(model.id)}:${escape(task.id)}" aria-label="${escape(label)}, ${escape(labels[index])}: ${escape(value)}" title="View measurement details">${escape(value)}</button>`;
    }).join('<span class="paired-value-arrow" aria-hidden="true">→</span>');
    return `<div class="paired-row" data-pair="${escape(id)}"><span class="paired-model">${escape(label)}</span><div class="paired-track" aria-hidden="true">${grid}<i class="paired-connector" style="left:${left}%;width:${width}%"></i><i class="paired-point first" style="left:${position(first.cell.value)}%"></i><i class="paired-point second" style="left:${position(second.cell.value)}%"></i></div><div class="paired-values">${values}</div></div>`;
  }).join("");

  const note = mode === "training"
    ? taskId === "prior" ? "Sequence probabilities from each checkpoint." : "Both checkpoints use embedding-fitted linear heads."
    : taskId === "atlas_profile" ? "Both readouts fit a linear head on the same source constructs."
      : taskId === "cell_selective" ? "Native outputs include held-locus slope calibration." : "The same model, evaluated through two readouts.";

  return `<div class="paired-plot" style="--category:${escape(color)}" role="group" aria-label="${escape(task.label)}: ${mode === "training" ? "before and after functional post-training" : "native outputs and embedding-fitted heads"}"><div class="paired-key"><span><i class="paired-key-point first" aria-hidden="true"></i>${escape(labels[0])}</span><span><i class="paired-key-point second" aria-hidden="true"></i>${escape(labels[1])}</span></div><div class="paired-axis-label"><span>${escape(axisLabels[taskId] || task.metric)}</span><span>${direction}</span></div><div class="paired-axis" aria-hidden="true"><div></div><div class="paired-axis-ticks">${ticks}</div><div></div></div>${rows}<div class="paired-note"><span>${note}</span></div>${omitted.length ? `<p class="paired-missing">No paired result: ${omitted.map(escape).join(", ")}.</p>` : ""}</div>`;
}
