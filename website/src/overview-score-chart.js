import { categoryScore, finite, ordered, overallScore, scoreCoverage, taskScore } from "./scoring.js";

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
const taskLabels = {
  prior:["Hidden-base", "loss"], opensplice:["Splicing", "effects"],
  context:["Cell", "contrast"], tissue_identification:["Tissue", "identification"],
  background:["Background", "interaction"], repair_percentile:["Single-edit", "rank"],
  cell_selective:["Cell", "selectivity"], atlas_profile:["Multi-cell", "gain"],
};
const categoryLabels = {priors:"Prior", prediction:"Function", context:"Context", interactions:"Interactions", design:"Design"};

export function overviewScoreContributions(data, modelId) {
  const available = data.categories.map(category => ({...category, score:categoryScore(data, modelId, category.id)}))
    .filter(category => finite(category.score));
  return available.map(category => ({...category, contribution:category.score / available.length}));
}

export function overviewTaskContributions(data, modelId) {
  const categories = overviewScoreContributions(data, modelId);
  return data.tasks.map(task => {
    const score = taskScore(data, modelId, task.id);
    const available = data.tasks.filter(t => t.categoryId === task.categoryId && finite(taskScore(data, modelId, t.id))).length;
    return {...task, contribution:finite(score) && available && categories.length ? score / available / categories.length : null};
  });
}

function taskDetails(data, model) {
  const contributions = overviewTaskContributions(data, model.id);
  // Preserve category groups when the compact table folds into two rows on phones.
  const groups = [data.categories.slice(0, 3), data.categories.slice(3)];
  return `<div class="overview-score-tooltip-heading">Weighted score</div><div class="overview-score-task-tables">${groups.map(categories => {
    const tasks = contributions.filter(task => categories.some(category => category.id === task.categoryId));
    return `<table><thead><tr class="overview-score-task-groups">${categories.map(category => `<th scope="colgroup" colspan="${tasks.filter(task => task.categoryId === category.id).length}" style="--category:${category.color}">${escape(categoryLabels[category.id] || category.label)}</th>`).join("")}</tr>
      <tr class="overview-score-task-labels">${tasks.map(task => `<th scope="col">${(taskLabels[task.id] || [task.label]).map(escape).join("<br>")}</th>`).join("")}</tr></thead>
      <tbody><tr>${tasks.map(task => {
        const category = categories.find(c => c.id === task.categoryId);
        const value = finite(task.contribution) ? task.contribution.toFixed(1).replace("-", "−") : "—";
        return `<td class="${!finite(task.contribution) ? "is-missing" : task.contribution <= 0 ? "is-nonpositive" : ""}" style="--category:${category.color}">${value}</td>`;
      }).join("")}</tr></tbody></table>`;
  }).join("")}</div>`;
}

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
  const breakdowns = new Map(models.map(model => [model.id, overviewScoreContributions(data, model.id)]));
  const scores = models.map((model) => overallScore(data, model.id)).filter(finite);
  const maximum = Math.ceil(Math.max(100, ...scores) / 50) * 50;
  const position = (value) => 100 * Math.max(0, value) / maximum;
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
    const visualScore = finite(score) ? Math.max(0, score) : 0;
    const height = position(visualScore);
    const parts = breakdowns.get(model.id);
    const positive = parts.filter(part => part.contribution > 0);
    const totalPositive = positive.reduce((sum, part) => sum + part.contribution, 0);
    let cursor = 0;
    // Cap negative visual weights at zero, retaining the original bar's total height.
    const segments = (visualScore > 0 ? positive : []).map(part => {
      const start = cursor;
      const size = visualScore * part.contribution / totalPositive;
      cursor += size;
      return `<span class="overview-score-segment" data-category="${part.id}" style="--segment-color:${part.color};--segment-start:${position(start)}%;--segment-size:${position(size)}%"></span>`;
    }).join("");
    return `<div class="overview-score-item is-${training} is-${readoutType}" data-score-model="${escape(model.id)}" tabindex="0" role="img" aria-label="${escape(`${label}, ${trainingLabel.toLowerCase()}, ${readout}: ${value}. ${covered}.`)}" style="--score-bottom:0%;--score-height:${height}%;--score-label:${height}%">
      <div class="overview-score-column" aria-hidden="true"><span class="overview-score-bar"></span><span class="overview-score-parts">${segments}</span><span class="overview-score-value">${value}</span></div>
      <div class="overview-score-name" aria-hidden="true">${modelLabel(model)}</div>
      <template>${taskDetails(data, model)}</template>
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
    <p class="sr-only" id="overview-score-description">Models are ordered from lowest to highest score. This score is a website summary, with 100 set by ${escape(referenceName)}. Task scores are averaged within categories, then available categories are averaged equally; missing results are omitted. Colour shows sequence-only or functional training. Solid bars indicate native outputs; diagonal hatching indicates fitted readouts. Hover or focus a model to see relative positive category contributions and each task's weighted contribution to its score. Negative categories have zero visual area; positive shares fill the unchanged bar. Task contributions retain their signs. In the multi-cell task, native outputs also receive a fitted linear head.</p>
    <div class="overview-score-plot">
      <div class="overview-score-grid" style="--model-count:${models.length};--reference-position:${position(100)}%;--zero-position:${position(0)}%">
        <div class="overview-score-scale" aria-hidden="true"><span style="--tick-position:${position(100)}%">100</span><span style="--tick-position:0%">0</span></div>
        <div class="overview-score-guides" aria-hidden="true"><span class="overview-score-reference"></span><span class="overview-score-zero"></span></div>
        <div class="overview-score-bars">${bars}</div>
      </div>
    </div>
  </figure>`;
}

export function initOverviewScoreInteractions(root) {
  const tooltip = document.createElement("div");
  tooltip.id = "overview-score-tooltip";
  tooltip.className = "overview-score-tooltip";
  tooltip.setAttribute("role", "tooltip");
  tooltip.hidden = true;
  document.body.append(tooltip);
  let active = null;
  const hide = () => {
    active?.classList.remove("is-active");
    active?.removeAttribute("aria-describedby");
    active = null;
    tooltip.hidden = true;
  };
  const show = item => {
    if (item === active) return;
    hide();
    active = item;
    item.classList.add("is-active");
    item.setAttribute("aria-describedby", tooltip.id);
    tooltip.innerHTML = item.querySelector("template").innerHTML;
    const viewportWidth = document.documentElement.clientWidth;
    tooltip.style.maxWidth = `${viewportWidth - 24}px`;
    tooltip.hidden = false;
    const bar = item.querySelector(".overview-score-bar").getBoundingClientRect();
    const scoreLabel = item.querySelector(".overview-score-value").getBoundingClientRect();
    const panel = tooltip.getBoundingClientRect();
    const horizontal = getComputedStyle(item).display === "grid";
    const anchorTop = horizontal ? Math.min(bar.top, scoreLabel.top)
      : Math.min(...[...root.querySelectorAll(".overview-score-value")].map(label => label.getBoundingClientRect().top));
    const left = Math.max(12, Math.min((bar.left + bar.right - panel.width) / 2, viewportWidth - panel.width - 12));
    const top = Math.max(8, anchorTop - panel.height - 10);
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  };
  const hoverItem = target => target instanceof Element
    ? target.closest(".overview-score-bar,.overview-score-name,.overview-score-segment,.overview-score-value")?.closest(".overview-score-item")
    : null;
  root.querySelectorAll(".overview-score-item").forEach(item => {
    item.addEventListener("pointerover", event => {
      if (hoverItem(event.target) === item) show(item);
    });
    item.addEventListener("pointerout", event => {
      if (active === item && hoverItem(event.relatedTarget) !== item) hide();
    });
    // Let the browser finish bringing a keyboard-focused bar into view first.
    item.addEventListener("focusin", () => requestAnimationFrame(() => {
      if (document.activeElement === item && item.matches(":focus-visible")) show(item);
    }));
    item.addEventListener("focusout", () => { if (active === item) hide(); });
    item.addEventListener("click", event => { if (event.pointerType === "touch") show(item); });
  });
  document.addEventListener("keydown", event => { if (event.key === "Escape") hide(); });
  document.addEventListener("pointerdown", event => {
    if (active && !active.contains(event.target) && !tooltip.contains(event.target)) hide();
  });
  window.addEventListener("scroll", event => { if (!tooltip.contains(event.target)) hide(); }, {passive:true, capture:true});
  window.addEventListener("resize", hide, {passive:true});
}
