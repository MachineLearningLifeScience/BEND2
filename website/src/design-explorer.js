const BUDGETS = [1, 5, 10, 25];
export const DEFAULT_DESIGN_MODELS = Object.freeze(["alphagenome", "ntv3_650m_post", "ntv3_650m_pre"]);
const COLORS = {
  alphagenome: "#be4d35",
  enformer: "#3b7b70",
  ntv3_650m_post: "#486e9a",
  ntv3_100m_post: "#8663a0",
  evo2_20b: "#9b7b35",
  generator_v2_3b: "#987370",
  ntv3_650m_pre: "#718958",
  onehot_resnet: "#587982",
  kmer_3_6: "#8b7561",
  uniform: "#99998f",
  experimental_reference: "#535962",
};
const escape = (value) => String(value ?? "").replace(
  /[&<>"']/g,
  (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character],
);
const percent = (value) => Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "—";
const dash = id => id === "uniform" ? ' stroke-dasharray="1 5"' : id === "experimental_reference" ? ' stroke-dasharray="10 6"' : "";
const marker = (item, cx, cy, r = 3.5, className = "", filled = false) => {
  const style = `fill="${filled || item.id === "uniform" ? item.color : "var(--design-marker-fill, #f4f1e9)"}" stroke="${item.color}" stroke-width="1.7"`;
  return item.id === "experimental_reference"
    ? `<path class="${className}" d="M ${cx} ${cy - r - 1} L ${cx + r + 1} ${cy} L ${cx} ${cy + r + 1} L ${cx - r - 1} ${cy} Z" ${style}/>`
    : `<circle class="${className}" cx="${cx}" cy="${cy}" r="${r}" ${style}/>`;
};

export function designSeries(data) {
  return (data.supplementary?.repairBudgets?.series || []).map((series) => {
    const model = data.models.find((item) => item.id === series.modelId);
    const readout = series.modelId === "uniform" ? "Random candidates"
      : model?.interface === "native" ? "Native outputs"
      : model?.kind === "baseline" && model?.interface === "fitted" ? "Fitted sequence features"
      : model?.interface === "fitted" ? "Embedding-fitted head"
      : model?.interface === "task-trained" ? "Task-trained model"
      : "";
    return {
      id: series.modelId,
      label: (model?.label || series.label).replace(/ · native$/, ""),
      readout,
      color: `var(--design-${series.modelId.replaceAll("_", "-")}, ${COLORS[series.modelId] || "#69736b"})`,
      points: BUDGETS.map((budget) => series.points.find((point) => point.budget === budget))
        .filter((point) => Number.isFinite(point?.successRate))
        .map((point) => ({ ...point })),
    };
  });
}

export function designExplorer(data, {
  models = DEFAULT_DESIGN_MODELS,
  active = "alphagenome",
  compact = false,
} = {}) {
  const available = designSeries(data);
  const availableIds = new Set(available.map((series) => series.id));
  const selectedIds = [...new Set(models)].filter((id) => id !== "uniform" && availableIds.has(id)).slice(0, 3);
  const series = [...selectedIds, "uniform"].map((id) => available.find((item) => item.id === id)).filter(Boolean);
  const reference = data.supplementary?.repairBudgets?.experimentalReference;
  if (reference) series.push({
    id: "experimental_reference",
    label: reference.label,
    readout: "Selected and evaluated using separate RNA measurements",
    color: `var(--design-experimental-reference, ${COLORS.experimental_reference})`,
    points: reference.points.filter(point => BUDGETS.includes(point.budget) && Number.isFinite(point.successRate)),
  });
  if (!series.length) return '<p class="design-empty">No budget measurements are available.</p>';
  active = series.some((item) => item.id === active) ? active : series[0].id;
  const width = compact ? 460 : 900, height = compact ? 310 : 370;
  const left = compact ? 44 : 48, right = compact ? 16 : 24, top = 25, bottom = 43;
  const x = value => left + (value - 1) / 24 * (width - left - right);
  const y = value => height - bottom - value * (height - top - bottom);
  // Leave gaps where a measurement or confidence bound is missing.
  const segments = (item, valid) => {
    const groups = [];
    let current = [];
    for (const count of BUDGETS) {
      const point = item.points.find(point => point.budget === count);
      if (point && valid(point)) current.push(point);
      else if (current.length) { groups.push(current); current = []; }
    }
    if (current.length) groups.push(current);
    return groups;
  };
  const intervals = series.map(item => item.points
    .filter(point => Number.isFinite(point.ciLow) && Number.isFinite(point.ciHigh))
    .map(point => `<g data-design-interval="${escape(item.id)}" data-design-interval-budget="${point.budget}" stroke="${item.color}" stroke-width="1" opacity=".55"><line x1="${x(point.budget)}" x2="${x(point.budget)}" y1="${y(point.ciLow)}" y2="${y(point.ciHigh)}"/><line x1="${x(point.budget) - 3}" x2="${x(point.budget) + 3}" y1="${y(point.ciLow)}" y2="${y(point.ciLow)}"/><line x1="${x(point.budget) - 3}" x2="${x(point.budget) + 3}" y1="${y(point.ciHigh)}" y2="${y(point.ciHigh)}"/></g>`).join("")).join("");
  const grid = [0, .25, .5, .75, 1].map(value => `<g><line class="design-grid-line" x1="${left}" x2="${width - right}" y1="${y(value)}" y2="${y(value)}" stroke="var(--design-grid, #d8d4c9)" stroke-width="1"/><text x="${left - 11}" y="${y(value) + 4}" text-anchor="end" class="design-axis-label">${value * 100}%</text></g>`).join("");
  const lines = series.map(item => `<g data-design-series="${escape(item.id)}">${segments(item, point => Number.isFinite(point.successRate)).map(points => `<polyline points="${points.map(point => `${x(point.budget)},${y(point.successRate)}`).join(" ")}" fill="none" stroke="${item.color}" stroke-width="${item.id === active ? 2.5 : 1.8}" opacity="${item.id === active || item.id === "uniform" || item.id === "experimental_reference" ? 1 : .8}"${dash(item.id)} stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>`).join("")}</g>`).join("");
  const tooltips = [];
  const points = BUDGETS.map(count => {
    const measurements = series.map(item => ({item, point:item.points.find(point => point.budget === count)})).filter(entry => entry.point);
    const descriptions = measurements.map(({item, point}) => {
      const ci = Number.isFinite(point.ciLow) && Number.isFinite(point.ciHigh) ? `95% confidence interval ${percent(point.ciLow)} to ${percent(point.ciHigh)}` : "Interval unavailable";
      return `${item.label}, ${item.readout}: ${percent(point.successRate)}; ${ci}.`;
    });
    const label = `${count} ${count === 1 ? "edit" : "edits"} tested. ${descriptions.join(" ")}`;
    const tooltipWidth = 248;
    const tooltipHeight = 42 + measurements.length * 22;
    const tooltipX = Math.max(left + 5, Math.min(x(count) + 16, width - right - tooltipWidth - 5));
    const tooltipY = count === 25 ? height - bottom - tooltipHeight - 5 : top + 8;
    const tooltipRows = measurements.map(({item, point}, i) => {
      return `<g data-design-result="${escape(item.id)}">${marker(item, 13, 45 + i * 22, 2.5, "", true)}<text x="23" y="${49 + i * 22}">${escape(item.label)}</text><text class="design-tooltip-value" x="${tooltipWidth - 12}" y="${49 + i * 22}" text-anchor="end">${percent(point.successRate)}</text></g>`;
    }).join("");
    tooltips.push(`<g class="design-point-tooltip" data-design-tooltip="${count}" aria-hidden="true" transform="translate(${tooltipX},${tooltipY})"><rect width="${tooltipWidth}" height="${tooltipHeight}" rx="3"/><text class="design-tooltip-heading" x="12" y="22">${count} ${count === 1 ? "edit" : "edits"}</text>${tooltipRows}</g>`);
    return `<g class="design-budget-points" role="group" tabindex="0" data-design-budget="${count}" aria-label="${escape(label)}"><rect class="design-budget-hit" x="${x(count) - 18}" y="${top - 8}" width="36" height="${height - top - bottom + 35}" fill="transparent"/>${measurements.map(({item,point}) => marker(item, x(count), y(point.successRate), 3.5, "design-observation")).join("")}</g>`;
  }).join("");
  const legend = `<div class="design-line-legend" role="group" aria-label="Highlight a curve">${series.map(item => `<button data-design-focus="${escape(item.id)}" aria-pressed="${item.id === active}" title="${escape(item.readout)} — highlight curve"><svg width="38" height="14" viewBox="0 0 38 14" aria-hidden="true"><line x1="1" x2="37" y1="7" y2="7" stroke="${item.color}" stroke-width="1.8" stroke-linecap="round"${dash(item.id)}/>${marker(item, 19, 7, 2.8)}</svg>${escape(item.label)}</button>`).join("")}</div>`;
  return `<div class="design-explorer"><div class="design-curve"><svg viewBox="0 0 ${width} ${height}" role="group" aria-label="Targets reached as more edits are tested. Hover or focus a measured budget for its results."><desc>Points show the four measured budgets; lines connect observations. Whiskers show pointwise 95% confidence intervals.</desc><text x="${left}" y="12" class="design-axis-label">Target responses reached</text>${grid}${BUDGETS.map(count => `<text x="${x(count)}" y="${height - bottom + 23}" text-anchor="middle" class="design-axis-label">${count}</text>`).join("")}<g class="design-measurements">${intervals}${lines}${points}</g>${tooltips.join("")}<text x="${(width + left - right) / 2}" y="${height - 2}" text-anchor="middle" class="design-axis-label">Edits tested per target</text></svg>${legend}</div></div>`;
}
