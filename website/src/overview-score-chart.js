import { finite, ordered, overallScore, scoreCoverage } from "./scoring.js";

const escape = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[character]);

// Model training is distinct from the benchmark's fitted/native readout.
// Groups follow manuscript tables/model-overview.tex and the model descriptions.
const trainingGroups = {
  evo2_20b: "sequence", ceno_1b_1m: "sequence", generator_v2_3b: "sequence",
  dnabert2: "sequence", ntv3_100m_pre: "sequence", ntv3_650m_pre: "sequence",
  ntv3_100m_post: "functional", ntv3_100m_native: "functional",
  ntv3_650m_post: "functional", ntv3_650m_native: "functional",
  alphagenome_fitted: "functional", alphagenome: "functional", enformer: "functional",
};
const trainingLabels = { sequence: "Sequence-only", functional: "Functionally trained", unknown: "Training not classified" };

function modelLabel(model) {
  const name = model.label.replace(/ · native$/, "");
  const displayName = escape(name).replace("AlphaGenome", "Alpha<wbr>Genome").replace("GENERATORv2", "GENERATOR<wbr>v2");
  const readout = model.interface === "native" ? "native" : "fitted";
  const ntv3 = name.match(/^(NTv3 \S+) (pre|post)$/);
  return ntv3
    ? `<span>${escape(ntv3[1])}</span><span class="overview-score-readout">${ntv3[2]} · ${readout}</span>`
    : `<span>${displayName}</span><span class="overview-score-readout">${readout}</span>`;
}

/** The overview shares the table's fixed-reference score and coverage rules. */
export function renderOverviewScoreChart(data) {
  const models = ordered(data.models.filter((model) => model.kind === "foundation"),
    (model) => overallScore(data, model.id), "lower");
  const scores = models.map((model) => overallScore(data, model.id)).filter(finite);
  const minimum = Math.floor(Math.min(0, ...scores) / 50) * 50;
  const maximum = Math.ceil(Math.max(100, ...scores) / 50) * 50;
  const span = maximum - minimum;
  const position = (value) => 100 * (value - minimum) / span;
  const reference = data.models.find((model) => model.id === data.scoring.referenceModelId);
  const referenceName = reference?.label ?? "reference model";
  const bars = models.map((model) => {
    const score = overallScore(data, model.id);
    const coverage = scoreCoverage(data, model.id);
    const value = finite(score) ? score.toFixed(1).replace("-", "−") : "—";
    const training = trainingGroups[model.id] ?? "unknown";
    const trainingLabel = trainingLabels[training];
    const readoutType = model.interface === "native" ? "native" : "fitted";
    const readout = readoutType === "native" ? "native outputs" : "fitted embedding heads";
    const label = model.label.replace(/ · native$/, "");
    const covered = `${coverage.tasks.complete} of ${coverage.tasks.total} tasks; ${coverage.categories.complete} of ${coverage.categories.total} categories`;
    const bottom = finite(score) ? position(Math.min(0, score)) : position(0);
    const height = finite(score) ? 100 * Math.abs(score) / span : 0;
    return `<div class="overview-score-item is-${training} is-${readoutType}" tabindex="0" role="img" aria-label="${escape(`${label}, ${trainingLabel.toLowerCase()}, ${readout}: ${value}. ${covered}.`)}" style="--score-bottom:${bottom}%;--score-height:${height}%;--score-label:${position(finite(score) ? score : 0)}%">
      <div class="overview-score-column" aria-hidden="true"><span class="overview-score-bar"></span><span class="overview-score-value">${value}</span></div>
      <div class="overview-score-name" aria-hidden="true">${modelLabel(model)}</div>
      <span class="overview-score-tooltip" aria-hidden="true"><strong>${coverage.tasks.complete}/${coverage.tasks.total} tasks · ${coverage.categories.complete}/${coverage.categories.total} categories</strong><span>${trainingLabel} · ${model.interface === "native" ? "native outputs" : "fitted heads"}</span></span>
    </div>`;
  }).join("");
  return `<figure class="overview-score-chart" aria-labelledby="overview-score-title" aria-describedby="overview-score-description">
    <figcaption class="overview-score-caption">
      <span id="overview-score-title">Combined score</span>
      <span class="overview-score-legend">
        <span class="overview-score-key"><span><i class="is-sequence" aria-hidden="true"></i>Sequence-only</span><span><i class="is-functional" aria-hidden="true"></i>Functionally trained</span></span>
        <span class="overview-score-key"><span><i class="is-native" aria-hidden="true"></i>Native outputs</span><span><i class="is-fitted" aria-hidden="true"></i>Fitted readouts</span></span>
      </span>
      <span class="overview-score-direction">Higher is better →</span>
    </figcaption>
    <p class="sr-only" id="overview-score-description">Models are ordered from lowest to highest score. This score is a website summary, with 100 set by ${escape(referenceName)}. Task scores are averaged within categories, then available categories are averaged equally; missing results are omitted. Colour shows sequence-only or functional training. Solid bars indicate native outputs; diagonal hatching indicates fitted readouts. In the multi-cell task, native outputs also receive a fitted linear head.</p>
    <div class="overview-score-plot">
      <div class="overview-score-grid" style="--model-count:${models.length};--reference-position:${position(100)}%;--zero-position:${position(0)}%">
        <div class="overview-score-scale" aria-hidden="true"><span style="--tick-position:${position(100)}%">100</span><span style="--tick-position:${position(0)}%">0</span>${minimum < 0 ? `<span style="--tick-position:0%">${minimum}</span>` : ""}</div>
        <div class="overview-score-guides" aria-hidden="true"><span class="overview-score-reference"></span><span class="overview-score-zero"></span></div>
        <div class="overview-score-bars">${bars}</div>
      </div>
    </div>
  </figure>`;
}
