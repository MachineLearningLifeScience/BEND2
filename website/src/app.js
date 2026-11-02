import {
  finite,
  indexData,
  taskScore,
  overallScore,
  scoreCoverage,
  coverage,
  ordered,
  ranks,
  csvCell,
} from "./scoring.js";
import { icon } from "./icons.js";
import { tableTintOpacity } from "./table-tint.js";
import { budgetExplorer } from "./budget.js";
import { explorerRows, taskExplorerChart } from "./explore-charts.js";
import { pairedChart } from "./paired-chart.js";
import { designExplorer, DEFAULT_DESIGN_MODELS } from "./design-explorer.js";
import { measurementDetail, referenceDetail, taskSummary } from "./measurement-detail.js";
import { initPageNavigation } from "./page-navigation.js";
import { initOverview } from "./overview.js";

const $ = (s) => document.querySelector(s);
const escape = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const shortCategories = {
  priors: "Prior",
  prediction: "Function",
  context: "Context",
  interactions: "Interactions",
  design: "Design",
};
const headings = {
  prior: ["Hidden-base", "loss"],
  opensplice: ["Splicing", "effects"],
  context: ["Cell", "contrast"],
  tissue_identification: ["Tissue", "identification"],
  background: ["Background", "interaction"],
  repair_percentile: ["Single-edit", "rank"],
  cell_selective: ["Cell", "selectivity"],
  atlas_profile: ["Multi-cell", "gain"],
};
const conciseUnits = {
  prior: "bits ↓",
  opensplice: "Spearman ↑",
  context: "Spearman ↑",
  tissue_identification: "top-1 % ↑",
  background: "Spearman ↑",
  repair_percentile: "percentile ↓",
  cell_selective: "log₂ utility ↑",
  atlas_profile: "log₂ gain ↑",
};
let data, lookup, lastFocus, lastFocusVisible, toastTimeout;
let renderedSearch = location.search;
const state = {
  category: "all",
  endpoint: "opensplice",
  view: "table",
  filter: "all",
  query: "",
  sort: "index",
  direction: "higher",
  baselines: false,
  dialog: null,
  exploreTask: "opensplice",
  exploreMode: "ranking",
  designModels: [...DEFAULT_DESIGN_MODELS],
  designActive: "alphagenome",
};
const fmt = (n, p = 1) => (finite(n) ? n.toFixed(p).replace("-", "−") : "—");
const modelTitle = (m) => m.label.replace(" · native", "");
const publicURL = (url) => {
  try { return new URL(url).protocol === "https:" ? url : ""; } catch { return ""; }
};
const submissionURL = (path) => /^submissions\/community-[a-z0-9-]+\.json$/.test(path || "")
  ? `https://github.com/MachineLearningLifeScience/BEND2/blob/main/${path}` : "";
const readout = (m) =>
  m.kind === "baseline" && m.interface === "fitted"
    ? "Fitted sequence features"
    : m.interface === "native"
      ? "Native outputs"
      : m.interface === "fitted"
        ? "Embedding-fitted head"
        : m.interface === "sequence"
          ? "Sequence baseline"
          : "Task-trained model";
const colorFor = (task) =>
  data.categories.find((c) => c.id === task.categoryId).color;
const getCell = (model, task) => lookup.measurements.get(`${model}:${task}`);
const raw = (model, task) => getCell(model, task)?.value ?? null;
const valueFor = (m) => state.sort === "name" ? null : state.sort === "index" ? overallScore(data, m.id) : raw(m.id, state.sort);
const visibleTasks = () => data.tasks;
const categoryFor = (id) => data.categories.find((c) => c.id === id);
function readURL() {
  const q = new URLSearchParams(location.search);
  state.exploreTask = lookup.tasks.has(q.get("explore")) ? q.get("explore") : "opensplice";
  state.exploreMode = ["ranking", "training", "readout"].includes(q.get("chart")) ? q.get("chart") : "ranking";
  if (state.exploreTask === "prior" && state.exploreMode === "readout") state.exploreMode = "ranking";
  const budgetIds = new Set(data.supplementary.repairBudgets.series.map(s => s.modelId));
  state.designModels = q.has("designModels") ? [...new Set(q.get("designModels").split(","))].filter(id => id !== "uniform" && budgetIds.has(id)).slice(0, 3) : [...DEFAULT_DESIGN_MODELS];
  const designReferences = data.supplementary?.repairBudgets?.experimentalReference ? ["uniform", "experimental_reference"] : ["uniform"];
  state.designActive = [...state.designModels, ...designReferences].includes(q.get("highlight")) ? q.get("highlight") : state.designModels[0] || "uniform";
  state.category = "all";
  state.view = "table";
  state.endpoint = lookup.tasks.has(q.get("endpoint"))
    ? q.get("endpoint")
    : "opensplice";
  state.sort =
    ["index", "name"].includes(q.get("sort")) || lookup.tasks.has(q.get("sort"))
      ? q.get("sort")
      : lookup.tasks.has(q.get("endpoint")) ? state.endpoint : "index";
  state.direction = ["lower", "higher"].includes(q.get("direction"))
    ? q.get("direction")
    : lookup.tasks.get(state.sort)?.direction || "higher";
  // Ignore obsolete search and readout parameters in saved URLs.
  state.filter = "all";
  state.query = "";
  state.baselines = q.get("baselines") === "1";
  state.dialog = lookup.tasks.has(q.get("task"))
    ? { type: "task", id: q.get("task") }
    : lookup.models.has(q.get("model"))
      ? { type: "model", id: q.get("model") }
      : null;
}
function syncURL() {
  const u = new URL(location.href);
  u.search = "";
  const p = u.searchParams;
  if (state.sort !== "index") p.set("sort", state.sort);
  if (state.sort !== "index" && state.endpoint !== "opensplice") p.set("endpoint", state.endpoint);
  if (state.direction !== (lookup.tasks.get(state.sort)?.direction || "higher"))
    p.set("direction", state.direction);
  if (state.baselines) p.set("baselines", "1");
  if (state.dialog?.type === "task") p.set("task", state.dialog.id);
  if (state.dialog?.type === "model") p.set("model", state.dialog.id);
  if (state.exploreTask !== "opensplice") p.set("explore", state.exploreTask);
  if (state.exploreMode !== "ranking") p.set("chart", state.exploreMode);
  if (state.designModels.join(",") !== DEFAULT_DESIGN_MODELS.join(",")) p.set("designModels", state.designModels.join(","));
  if (state.designActive !== (state.designModels[0] || "uniform")) p.set("highlight", state.designActive);
  history.replaceState(null, "", u);
  renderedSearch = u.search;
}
function filteredModels(includeBaselines = false) {
  return data.models.filter((model) => includeBaselines
    ? model.kind !== "foundation"
    : model.kind === "foundation");
}
function sortedModels(items) {
  return state.sort === "name"
    ? [...items].sort(
        (a, b) =>
          modelTitle(a).localeCompare(modelTitle(b)) *
          (state.direction === "higher" ? 1 : -1),
      )
    : ordered(items, valueFor, state.direction);
}
function render() {
  const focused = document.activeElement;
  const key = focused?.dataset?.action === "baselines" ? "action" : ["focusTask", "sort"].find(
    (k) => focused?.dataset?.[k],
  );
  const value = key ? focused.dataset[key] : null;
  renderTable();
  syncURL();
  if (key && !focused.isConnected)
    document
      .querySelector(
        `[data-${key.replace(/[A-Z]/g, (c) => "-" + c.toLowerCase())}="${CSS.escape(value)}"]`,
      )
      ?.focus({ preventScroll: true });
}
function chooseTask(id) {
  if (!lookup.tasks.has(id)) return;
  state.endpoint = id;
  state.sort = id;
  state.direction = lookup.tasks.get(id).direction;
  render();
}
function tint(task, value) {
  if (!finite(value)) return "";
  const values = data.models
    .filter((m) => m.kind === "foundation")
    .map((m) => raw(m.id, task.id));
  const amount = tableTintOpacity(task, value, values);
  const h = colorFor(task);
  return `rgba(${parseInt(h.slice(1, 3), 16)},${parseInt(h.slice(3, 5), 16)},${parseInt(h.slice(5, 7), 16)},${amount})`;
}
function metricButton(model, task) {
  const m = getCell(model.id, task.id),
    missing = !finite(m?.value),
    special = task.id === "atlas_profile" && model.interface === "native";
  const title = (missing
    ? m?.missingReason || (m?.status === "unsupported"
      ? "Not applicable to this interface"
      : m?.status === "not_evaluated" ? (m.notes?.[0] || "Not evaluated in this submission") : "Result not available")
    : m.uncertainty
      ? `95% interval: ${fmt(m.uncertainty.low, task.precision)}–${fmt(m.uncertainty.high, task.precision)}. Click for details.`
      : "Click for the evaluation setting and source.") + (special && !missing ? " Fitted head using native-output features." : "") + (m?.verification ? ` ${m.verification.label}.` : "");
  return `<button class="score-cell${missing ? " missing" : ""}" data-cell="${model.id}:${task.id}" style="--tint:${tint(task, m?.value)};--category:${colorFor(task)}" title="${escape(title)}" aria-label="${escape(model.label)}, ${escape(task.label)}: ${missing ? escape(title) : escape(m.displayValue)}">${missing ? "—" : escape(m.displayValue)}</button>`;
}
function renderTable() {
  const tasks = data.tasks,
    models = sortedModels(filteredModels()),
    base = sortedModels(filteredModels(true)),
    task = lookup.tasks.get(state.endpoint),
    colCount = 2 + tasks.length;
  const rankTask = lookup.tasks.get(state.sort);
  const rankLabel = rankTask ? rankTask.label : "Combined score";
  const modelRanks = ranks(models,
    m => rankTask ? raw(m.id, rankTask.id) : overallScore(data, m.id),
    rankTask?.direction || "higher");
  const rankMark = (m) => {
    if (m.kind !== "foundation") return '<span class="model-rank-spacer" aria-hidden="true"></span>';
    const rank = modelRanks.get(m.id);
    const label = rank ? `${rankLabel}: rank ${rank} among genomic model/readout entries` : `${rankLabel}: no result to rank`;
    return `<span class="model-rank${rank && rank <= 3 ? ` rank-leading rank-${rank}` : ""}${rank ? "" : " rank-unavailable"}" title="${escape(label)}"><span class="sr-only">${escape(label)}</span><span aria-hidden="true">${rank && rank <= 3 ? `<img class="rank-art" src="./assets/ranks/rank-${rank}.svg" alt="" width="40" height="40">` : ""}<span class="rank-number">${rank || "—"}</span></span></span>`;
  };
  const sortMark = (id) => state.sort === id
    ? '<span class="sort-order" aria-hidden="true"><i></i><i></i><i></i></span>' : "";
  const maxIndex = Math.max(100, ...data.models.map(m => overallScore(data,m.id)).filter(finite));
  const combinedCell = (m) => {
    const score = overallScore(data,m.id), cov = scoreCoverage(data,m.id);
    const partial = cov.tasks.complete < cov.tasks.total;
    const description = `${partial ? 'Partial' : 'Combined'} score: ${fmt(score)}; ${cov.tasks.complete} of ${cov.tasks.total} tasks, ${cov.categories.complete} of ${cov.categories.total} categories`;
    return `<td class="index-cell" title="${description}"><button class="index-score" data-action="score" aria-label="${escape(m.label)}, ${description}">${fmt(score)}</button>${finite(score) ? `<div class="index-bar" aria-hidden="true"><i style="width:${Math.max(0,100*score/maxIndex)}%"></i></div>` : ''}</td>`;
  };
  let html = `<table class="results-table" aria-label="BEND 2.0 benchmark results" style="--active-category:${colorFor(task)}">
    <colgroup><col class="model-col"><col class="index-col">${tasks.map(() => '<col class="score-col">').join("")}</colgroup>
    <thead><tr class="group-row"><th></th><th class="index-group">Overall</th>${data.categories.map((c) => `<th class="group" colspan="${tasks.filter((t) => t.categoryId === c.id).length}" scope="colgroup" style="--category:${c.color}">${shortCategories[c.id]}</th>`).join("")}</tr>
    <tr class="task-row">
      <th class="model-header" aria-sort="${state.sort === "name" ? (state.direction === "higher" ? "ascending" : "descending") : "none"}"><div class="model-heading"><span class="rank-heading" title="${escape(rankLabel)} ranking">Rank</span><button data-sort="name" aria-label="Sort by model name"><span class="sort-label">Model / readout</span></button></div>${sortMark("name")}</th>
      <th class="index-heading" style="--category:var(--forest)" aria-sort="${state.sort === "index" ? (state.direction === "higher" ? "descending" : "ascending") : "none"}"><button class="task-label" data-sort="index" aria-label="Sort by combined score"><span class="sort-label">Combined<br>score</span></button><div class="heading-meta"><span>100 = NTv3 ref.</span><button class="task-info" data-action="score" aria-label="About the combined score" title="Combined score definition">${icon("info",12)}</button></div>${sortMark("index")}</th>
      ${tasks.map((t) => `<th scope="col" class="metric-heading" style="--category:${colorFor(t)}" aria-sort="${state.sort === t.id ? (state.direction === "higher" ? "descending" : "ascending") : "none"}"><button class="task-label" data-focus-task="${t.id}" aria-label="Sort by ${escape(t.label)}"><span class="sort-label">${headings[t.id].join("<br>")}</span></button><div class="heading-meta"><span>${conciseUnits[t.id]}</span><button class="task-info" data-task="${t.id}" aria-label="About ${escape(t.label)}" title="Task definition">${icon("info",12)}</button></div>${sortMark(t.id)}</th>`).join("")}
    </tr></thead><tbody>`;
  const row = (m) => `<tr data-row="${m.id}"><td class="model-cell"><div class="model-identity">${rankMark(m)}<div class="model-description"><button class="model-name" data-model="${m.id}" aria-label="${escape(modelTitle(m))} (${escape(readout(m))})">${escape(modelTitle(m))}</button><span class="model-sub" title="${escape(readout(m))}">${m.origin === "community" ? (m.reviewStatus === "pending" ? "Awaiting review · " : "Community · ") : ""}${escape(readout(m))}</span></div></div></td>${combinedCell(m)}${tasks.map((t) => `<td class="metric-cell">${metricButton(m, t)}</td>`).join("")}</tr>`;
  const invitationAfter = Math.min(8, models.length);
  html += models.slice(0, invitationAfter).map(row).join("");
  html += `<tr class="model-invitation-row"><td colspan="${colCount}"><span class="invitation-slots" style="--task-count:${tasks.length}" aria-hidden="true"><span></span><span class="invitation-combined-slot"><i></i></span>${tasks.map(() => '<span><i></i></span>').join("")}</span><div class="model-invitation"><span class="model-invitation-gutter" aria-hidden="true"><span></span></span><a class="model-invitation-copy" href="https://github.com/MachineLearningLifeScience/BEND2/blob/main/docs/submitting.md" target="_blank" rel="noopener noreferrer" aria-label="Add your model — evaluation and submission guide"><span class="model-invitation-title">Add your model</span><span class="model-invitation-guide">Submission guide <span aria-hidden="true">↗</span></span></a></div></td></tr>`;
  html += models.slice(invitationAfter).map(row).join("");
  html += `<tr class="baseline-disclosure-row"><td colspan="${colCount}"><button id="baseline-toggle" class="baseline-disclosure" data-action="baselines" aria-expanded="${state.baselines}" aria-controls="baseline-rows"><span class="baseline-disclosure-label"><span class="disclosure-gutter" aria-hidden="true"><span class="disclosure-mark"></span></span><span>Baselines &amp; specialists</span></span></button></td></tr></tbody><tbody id="baseline-rows" class="${state.baselines ? "is-expanded" : ""}"${state.baselines ? "" : ' inert aria-hidden="true"'}>${base.map(row).join("")}</tbody><tbody>`;
  html += `<tr class="reference-row"><td class="model-cell"><div class="model-identity"><span class="model-rank-spacer" aria-hidden="true"></span><button class="model-name" data-action="references">Experimental reference</button></div></td><td class="index-cell">—</td>${tasks.map(t => {const r = data.references.find(r => r.taskId === t.id);return `<td class="metric-cell">${r ? `<button class="score-cell" data-reference="${t.id}" style="--tint:${tint(t,r.value)};--category:${colorFor(t)}" aria-label="${escape(t.label)} experimental reference ${r.displayValue}">${r.displayValue}</button>` : "—"}</td>`;}).join("")}</tr></tbody></table>`;
  $("#table-wrapper").innerHTML = html;
  // Clip cell contents, keeping native table columns and sticky model cells intact.
  $("#baseline-rows").querySelectorAll("td").forEach(cell => {
    const content = document.createElement("div");
    content.className = "baseline-cell-content";
    content.append(...cell.childNodes);
    const reveal = document.createElement("div");
    reveal.className = "baseline-cell-reveal";
    reveal.append(content);
    cell.append(reveal);
  });
  updateTableOverflow();
}
function dialogFrame(title, context, body) {
  return `<div class="dialog-head"><div><h2 id="dialog-title">${escape(title)}</h2>${context ? `<p class="dialog-context">${escape(context)}</p>` : ""}</div><button class="close-button" data-action="close" aria-label="Close dialog">${icon("close", 23)}</button></div><div class="dialog-body">${body}</div>`;
}
function openDialog(type, id, extra) {
  if (!$("#detail-dialog").open) {
    lastFocus = document.activeElement;
    lastFocusVisible = lastFocus?.matches(":focus-visible");
  }
  state.dialog = { type, id, extra };
  let html = "";
  if (type === "budget")
    html = dialogFrame(
      "Targets reached",
      "",
      budgetExplorer(data, extra || 10),
    );
  if (type === "method") html = methodDialog();
  if (type === "score") html = scoreDialog();
  if (type === "model") html = modelDialog(id);
  if (type === "task") html = taskDialog(id);
  if (type === "cell") html = cellDialog(id, extra);
  if (type === "reference") html = referenceDialog(id);
  if (type === "sources") html = sourcesDialog();
  if (type === "submission") html = submissionDialog();
  if (type === "references") html = referencesDialog();
  $("#dialog-content").innerHTML = html;
  const dialog = $("#detail-dialog");
  dialog.classList.toggle("budget-dialog", type === "budget");
  dialog.dataset.type = type;
  if (!dialog.open) dialog.showModal();
  dialog.scrollTop = 0;
  dialog.querySelector(".close-button").focus({ preventScroll: true });
  syncURL();
}
function closeDialog() {
  state.dialog = null;
  $("#detail-dialog").close();
  syncURL();
  if (lastFocus?.isConnected) {
    // Escape should not add a keyboard ring to a pointer-opened control.
    lastFocus.toggleAttribute("data-pointer-return", !lastFocusVisible);
    lastFocus.focus({ preventScroll: true });
  }
}
function scoreDialog() {
  return dialogFrame("Combined score", "",
    `<div class="score-definition"><p>NTv3 650M post sets the reference at 100, giving all eight tasks a common relative scale.</p>
    <div class="score-formula" role="img" aria-label="100 times the result minus baseline, divided by the NTv3 reference minus baseline"><span>100 ×</span><span class="score-fraction"><span>result − baseline</span><span>NTv3 reference − baseline</span></span></div>
    <p>We average task scores within each category, then give the available categories equal weight. Missing results are omitted.</p>
    <details class="dialog-details"><summary>Calculation details</summary><div>
    <p>The five categories are Sequence priors, Function, Context, Interactions and Design. Missing results never count as zero; task and category coverage is available on hover and in the CSV download.</p>
    <p>Each task uses a fixed baseline. Scores can exceed 100 or fall below zero. Experimental references are shown separately and do not set the scale.</p>
    <p>This combined score is a website proposal, not a result reported in the manuscript.</p>
    <table class="protocol-table"><thead><tr><th>Task</th><th>Baseline</th><th>NTv3 reference</th></tr></thead><tbody>${data.tasks.map((t) => `<tr><td>${escape(t.label)}</td><td>${fmt(t.baseline.value, t.precision)}</td><td>${fmt(raw(data.scoring.referenceModelId, t.id), t.precision)}</td></tr>`).join("")}</tbody></table>
    </div></details></div>`);
}
function methodDialog() {
  return dialogFrame("Reading the results", "",
    `<p>The table reports eight task measurements from the paper and reviewed community submissions in their original units.</p>
    <dl class="dialog-definitions"><div><dt>Fitted readouts</dt><dd>Linear predictors fitted to frozen model representations.</dd></div><div><dt>Native outputs</dt><dd>Released functional predictions, with task-specific calibration. Multi-cell design uses a linear head fitted to those outputs.</dd></div><div><dt>Uncertainty</dt><dd>Reported 95% confidence intervals appear where available. Multi-cell RNA repeats are separate measurements, not confidence intervals.</dd></div><div><dt>Experimental references</dt><dd>Task-specific comparisons using experimental measurements. They are not performance ceilings.</dd></div></dl>
    <div class="dialog-links"><button data-action="score">Combined score</button><button data-action="sources">Data sources</button></div>`);
}
function modelDialog(id) {
  const m = lookup.models.get(id),
    cov = coverage(data, id);
  const source = data.sources.find(s => s.submissionPath === m.submissionPath && m.submissionPath);
  const links = [
    [publicURL(m.url), "Model / checkpoint"],
    [publicURL(source?.url), "Evaluation evidence"],
    [submissionURL(m.submissionPath), "Submission record"],
  ].filter(([url]) => url).map(([url, label]) => `<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">${label} ↗</a>`).join(" · ");
  const contribution = m.origin === "community"
    ? `<p class="model-detail-line">Community submission · ${links}</p><details class="score-method"><summary>Model declaration</summary><p>Checkpoint revision: <code>${escape(m.declarations?.revision)}</code></p><p>Training data: ${escape(m.declarations?.training_data)}</p>${m.declarations?.pooling ? `<p>Pooling: ${escape(m.declarations.pooling)}</p>` : ""}${source?.sha256 ? `<p>Evidence SHA256: <code>${escape(source.sha256)}</code></p>` : ""}</details>` : "";
  return dialogFrame(
    modelTitle(m),
    `${readout(m)} · ${cov.complete} of ${cov.total} tasks`,
    `${contribution}<table class="model-score-table"><tbody>${data.tasks
      .map((t) => {
        const cell = getCell(id, t.id);
        return `<tr><td><button data-cell="${id}:${t.id}"><i class="category-dot" style="--category:${colorFor(t)}"></i>${escape(t.label)}</button></td><td>${escape(cell.displayValue)}</td><td>${conciseUnits[t.id]}</td></tr>`;
      })
      .join(
        "",
      )}</tbody></table><details class="dialog-details"><summary>Model details</summary><div><p>${escape(m.description)}</p><p>${escape(m.parameterLabel || "Parameter count not specified")}</p>${m.interface === "native" && (finite(raw(id,"atlas_profile")) || finite(raw(id,"cell_selective"))) ? `<p>${finite(raw(id,"atlas_profile")) ? "Multi-cell results use a linear head fitted to native outputs. " : ""}${finite(raw(id,"cell_selective")) ? "Cell-selective results include held-locus calibration." : ""}</p>` : ""}</div></details>`,
  );
}
function taskDialog(id) {
  const t = lookup.tasks.get(id);
  const cat = categoryFor(t.categoryId);
  const ds = data.datasets.find((d) => d.id === t.datasetId);
  let models = data.models.filter(
    (m) => m.kind === "foundation" && finite(raw(m.id, id)),
  );
  models = ordered(models, (m) => raw(m.id, id), t.direction);
  const base = data.models.filter(
    (m) => m.kind !== "foundation" && finite(raw(m.id, id)),
  );
  const ref = data.references.find((r) => r.taskId === id);
  const chartEntries = [
    ...models.map((m) => ({
      model: m,
      cell: getCell(m.id, id),
      kind: "model",
    })),
    ...base.map((m) => ({
      model: m,
      cell: getCell(m.id, id),
      kind: "baseline",
    })),
    ...(ref ? [{ model: null, cell: ref, kind: "reference" }] : []),
  ].sort(
    (a, b) =>
      (a.cell.value - b.cell.value) * (t.direction === "lower" ? 1 : -1),
  );
  const all = [...models, ...base].map((m) => getCell(m.id, id));
  if (ref) all.push(ref);
  const values = all
    .flatMap((m) => [m.value, m.uncertainty?.low, m.uncertainty?.high])
    .concat(
      id === "atlas_profile"
        ? (data.supplementary?.multiCellRepeats?.points || []).flatMap(
            (p) => p.repeatValues,
          )
        : [],
    )
    .filter(finite);
  const min = Math.min(0, t.baseline.value, ...values),
    max = Math.max(t.baseline.value, ...values) * 1.06 || 1;
  const range = max - min;
  const percent = (v) => ((v - min) / range) * 100;
  const zero = percent(0);
  function chartRow(m, cell, kind = "model") {
    const title =
      kind === "reference"
        ? id === "background"
          ? "HepG2–K562 transfer"
          : "Experimental reference"
        : modelTitle(m) + (m.interface === "native" ? " · native" : "");
    const c = cell.uncertainty;
    const reps = data.supplementary?.multiCellRepeats?.points?.find(
      (p) => p.modelId === (m?.id || "experimental_reference"),
    );
    return `<div class="chart-row ${kind}" style="--category:${cat.color}"><button ${kind === "reference" ? `data-reference="${id}"` : `data-cell="${m.id}:${id}"`} title="${escape(title)}">${escape(title)}</button><div class="chart-track"><i class="chart-zero" style="left:${zero}%"></i><span class="chart-bar" style="left:${Math.min(zero, percent(cell.value))}%;width:${Math.abs(percent(cell.value) - zero)}%"></span>${c ? `<span class="ci-line" style="left:${percent(c.low)}%;width:${((c.high - c.low) / range) * 100}%"></span>` : ""}${id === "atlas_profile" && reps ? reps.repeatValues.map((v, i) => `<i class="repeat-dot repeat-${i}" style="left:${percent(v)}%" title="RNA repeat ${i + 1}: ${fmt(v, 3)}"></i>`).join("") : ""}</div><span>${escape(cell.displayValue)}</span></div>`;
  }
  return dialogFrame(
    t.label,
    ds?.shortLabel || ds?.label || t.datasetId,
    `<p>${escape(taskSummary(t))}</p><div class="task-chart"><p class="dialog-plot-label">${escape(t.metric)} · ${t.direction === "higher" ? "Higher" : "Lower"} is better</p><div class="chart-axis"><span>${fmt(min, min < 0 ? 1 : 0)}</span><span>${fmt((min + max) / 2, 2)}</span><span>${fmt(max, 2)}</span></div>${chartEntries.map((r) => chartRow(r.model, r.cell, r.kind)).join("")}</div><p class="chart-note">${id === "atlas_profile" ? "Markers show the two RNA measurements." : "Whiskers show reported 95% confidence intervals."}</p>
    ${id === "repair_percentile" ? '<div class="dialog-links"><button data-action="budget">Results by testing budget</button></div>' : ""}
    <details class="dialog-details"><summary>Evaluation details</summary><div><p>${escape(t.description)}</p><p>${escape(t.cohort)}</p>${t.cautions?.filter((c) => !c.includes("superseded") && !c.includes("Original confirmatory")).map(c => `<p>${escape(c)}</p>`).join("") || ""}<p>Gray rows show baselines and experimental references. ${id === "atlas_profile" ? "RNA repeats are separate measurements, not confidence intervals." : "Intervals describe individual estimates, not the significance of differences between models."}</p><p>Manuscript ${escape(t.figure)}. Select a result for its method and source records.</p></div></details>`,
  );
}
function cellDialog(modelId, taskId) {
  const detail = measurementDetail(data, modelId, taskId);
  return dialogFrame(detail.title, detail.eyebrow, detail.body);
}
function referenceDialog(taskId) {
  const detail = referenceDetail(data, taskId);
  return dialogFrame(detail.title, detail.eyebrow, detail.body);
}
function referencesDialog() {
  return dialogFrame("Experimental references", "",
    `<p>These task-specific comparisons use experimental measurements. They are not performance ceilings.</p><table class="model-score-table"><tbody>${data.tasks.filter(t => t.reference).map(t => `<tr><td><button data-reference="${t.id}">${escape(t.label)}</button></td><td>${fmt(t.reference.value, t.precision)}</td><td>${conciseUnits[t.id]}</td></tr>`).join("")}</tbody></table>`);
}
function sourcesDialog() {
  return dialogFrame("Data sources", "",
    `<p>Results come from manuscript Table 1 and documented website additions. The downloads retain source estimates and available uncertainty intervals.</p>
    <table class="protocol-table"><tbody><tr><td>Complete benchmark</td><td><a href="./data/benchmark.json" download>JSON ↓</a></td></tr><tr><td>Source and protocol notes</td><td><a href="./data/sources.md">Read notes</a></td></tr>${data.sources.filter(s => s.snapshotPath).map(s => `<tr><td>${escape(s.title)}</td><td><a href="./${escape(s.snapshotPath)}" download>Download ↓</a></td></tr>`).join("")}</tbody></table>
    <details class="dialog-details"><summary>Provenance</summary><div><p>Published measurements are preserved at manuscript precision. Later evaluations and interface checks are documented separately.</p><dl class="dialog-definitions"><div><dt>Snapshot</dt><dd><code>${escape(data.source.commit)}</code></dd></div><div><dt>Extracted</dt><dd>${escape(data.source.extractedOn)}</dd></div><div><dt>Table SHA-256</dt><dd><code>${escape(data.source.tableSha256)}</code></dd></div></dl></div></details>`);
}
function submissionDialog() {
  return dialogFrame(
    "Add your model",
    "Leaderboard contribution",
    `<p class="dialog-lede">Submit results for any subset of tasks.</p>
    <h3>1. Evaluate your model</h3>
    <p>Follow the <a href="https://github.com/MachineLearningLifeScience/BEND2/blob/main/README.md" target="_blank" rel="noopener noreferrer">README</a> to install BEND and create your adapter. Atlas uses short sequences and includes the data in the package.</p>
    <pre><code>bend2 run my_model.py --tasks atlas_profile --output results/my-model</code></pre>
    <h3>2. Submit for review</h3>
    <p>After the public release, install GitHub CLI, sign in, and run:</p>
    <pre><code>bend2 submit results/my-model --github \\
  --model-url https://huggingface.co/your-lab/your-model</code></pre>
    <p>The command uploads an evidence ZIP to your BEND fork and opens a pull request with the result record. Maintainers check the model setup and rescore every submitted task. Accepted results are labelled “Contributor evaluated.” Tasks rerun independently by BEND receive “Reproduced by BEND.” Your row appears after the PR is merged and the website rebuilds.</p>
    <p>During private development, provide <code>--github OWNER/REPO</code> with a public repository you can write to. The <a href="https://github.com/MachineLearningLifeScience/BEND2/blob/main/docs/submitting.md" target="_blank" rel="noopener noreferrer">submission guide</a> explains the options.</p>
    <div class="participate-actions"><a class="dark-button" style="color:var(--paper)" href="https://github.com/MachineLearningLifeScience/BEND2/blob/main/docs/submitting.md" target="_blank" rel="noopener noreferrer">Submission guide ↗</a><a href="https://github.com/MachineLearningLifeScience/BEND2/tree/main/submissions" target="_blank" rel="noopener noreferrer">Reviewed submissions ↗</a></div>
    <p>To host evidence elsewhere, export it and use <code>bend2 submit --evidence-url</code>, then open a PR with the generated JSON. You can also <a href="https://github.com/MachineLearningLifeScience/BEND2/issues/new?template=model.yml" target="_blank" rel="noopener noreferrer">send the generated JSON and evidence link in a submission issue</a> for maintainer help.</p>`,
  );
}
function toast(message) {
  clearTimeout(toastTimeout);
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  toastTimeout = setTimeout(() => ($("#toast").hidden = true), 3300);
}
function downloadRows(models, tasks, name) {
  const lines = [
    [
      "model_id",
      "model",
      "readout",
      `reference_index_${data.scoring.defaultTaskIds.length}_tasks`,
      "combined_tasks_evaluated",
      "combined_tasks_total",
      "combined_categories_evaluated",
      "combined_categories_total",
      ...tasks.flatMap((t) => [
        t.id,
        `${t.id}_status`,
        `${t.id}_ci_low`,
        `${t.id}_ci_high`,
        `${t.id}_verification`,
      ]),
    ],
  ];
  for (const m of models)
    lines.push([
      m.id,
      m.label,
      readout(m),
      overallScore(data, m.id),
      scoreCoverage(data, m.id).tasks.complete,
      scoreCoverage(data, m.id).tasks.total,
      scoreCoverage(data, m.id).categories.complete,
      scoreCoverage(data, m.id).categories.total,
      ...tasks.flatMap((t) => {
        const c = getCell(m.id, t.id);
        return [c.value, c.status, c.uncertainty?.low, c.uncertainty?.high, c.verification?.status || (m.origin === "community" ? "not_evaluated" : "paper_result")];
      }),
    ]);
  const csv = lines.map((r) => r.map(csvCell).join(",")).join("\r\n");
  const url = URL.createObjectURL(
    new Blob([csv], { type: "text/csv;charset=utf-8;" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast("Results downloaded.");
}
const exploreNames = {
  prior: "Hidden-base prediction", opensplice: "Splicing effects",
  context: "Cell-type differences", tissue_identification: "Tissue identification",
  background: "Background interactions", repair_percentile: "Single-edit ranking",
  cell_selective: "Cell-selective expression", atlas_profile: "Multi-cell design",
};
const exploreCopy = {
  prior: "Predict a hidden base from the surrounding DNA. Lower loss means better sequence probabilities.",
  opensplice: "Predict how a mutation changes splicing in genes held out of readout fitting.",
  context: "Predict the difference in a mutation’s expression effect between HepG2 and K562 cells.",
  tissue_identification: "Match a predicted expression profile across held-out genes to the correct tissue.",
  background: "Predict how the same mutation’s effect changes between two genetic backgrounds.",
  repair_percentile: "Choose a single-base edit that matches a reference edit’s effect. Evaluate the first choice’s measured rank among candidates.",
  cell_selective: "Choose an edit that increases expression in one cell type while changing expression as little as possible in the other.",
  atlas_profile: "Choose ten enhancers with activity in the requested cells and little activity elsewhere. Measure gain over matched random selection.",
};
function renderExplorer() {
  const task = lookup.tasks.get(state.exploreTask), category = categoryFor(task.categoryId);
  const description = exploreCopy[task.id];
  if (task.id === "prior" && state.exploreMode === "readout") state.exploreMode = "ranking";
  const rail = $("#task-rail");
  if (!rail.children.length) rail.innerHTML = data.categories.map(c => `<div class="task-rail-group" style="--category:${c.color}"><span>${escape(c.label)}</span>${data.tasks.filter(t => t.categoryId === c.id).map(t => `<button data-explore-task="${t.id}" aria-pressed="${t.id === task.id}">${escape(exploreNames[t.id])}<span aria-hidden="true">›</span></button>`).join("")}</div>`).join("");
  rail.querySelectorAll("[data-explore-task]").forEach(button => {
    button.setAttribute("aria-pressed", String(button.dataset.exploreTask === task.id));
  });
  $("#explore-heading").innerHTML = `<div class="explore-heading" style="--category:${category.color}"><h3>${escape(exploreNames[task.id])}</h3><button class="inline-task-details" data-task="${task.id}" title="${escape(description)}" aria-label="About ${escape(exploreNames[task.id])}"><span class="task-details-label">Task details ↗</span><span class="task-details-symbol" aria-hidden="true">${icon("info",16)}</span></button></div>`;
  document.querySelectorAll("[data-explore-mode]").forEach(button => {
    button.setAttribute("aria-pressed", String(button.dataset.exploreMode === state.exploreMode));
    button.disabled = task.id === "prior" && button.dataset.exploreMode === "readout";
    button.title = button.disabled ? "This task evaluates sequence probabilities, not fitted readouts." : "";
  });
  const ranking = state.exploreMode === "ranking";
  $("#explore-options").innerHTML = ranking ? `<div class="explore-options"><span>${escape(conciseUnits[task.id])}<span class="explore-direction">${task.direction === "lower" ? "Lower" : "Higher"} is better</span></span></div>` : "";
  if (ranking) {
    const options = {showBaselines: true};
    const { rows, omitted } = explorerRows(data, task.id, options);
    $("#explore-chart").innerHTML = taskExplorerChart(data, task.id, options);
    const missing = omitted.length ? `<details class="explore-missing"><summary>${omitted.length} without a result</summary><p>${omitted.map(m => `${escape(modelTitle(m))} (${escape(task.id === "prior" ? "sequence probabilities" : readout(m))})`).join("; ")}</p></details>` : "";
    $("#explore-notes").innerHTML = `<div class="explore-notes"><span>${task.id === "atlas_profile" ? "Filled and open dots: two RNA measurements of the same sequences. Bars show their mean." : rows.some(r => r.cell.uncertainty) ? "Black whiskers: reported 95% intervals. Click a result for details." : "Click a result for its evaluation setting and source."}</span>${missing}</div>`;
  } else {
    $("#explore-chart").innerHTML = pairedChart(data, task.id, state.exploreMode);
    $("#explore-notes").innerHTML = "";
  }
  syncURL();
}
function renderDesign(focusSelector) {
  const pickerOpen = $("#design-content .design-model-picker")?.open;
  $("#design-content").innerHTML = designExplorer(data, {models:state.designModels, active:state.designActive, compact:$("#design-content").clientWidth < 600});
  if (pickerOpen) $("#design-content .design-model-picker").open = true;
  document.dispatchEvent(new CustomEvent('design:render'));
  if (focusSelector) $(focusSelector)?.focus({preventScroll:true});
  syncURL();
}
let citationText = "";
fetch($("#citation-download").href).then(async (response) => {
  if (!response.ok) return;
  citationText = await response.text();
  $("#bibtex-citation").innerHTML = citationText.trimEnd().split("\n").map(line =>
    `<span class="citation-line">${escape(line).replace(/^(\s*)(title|author|year)(\s*=)/, '$1<span class="citation-key">$2</span>$3')}</span>`
  ).join("\n");
  $(".citation-code").hidden = false;
  $('[data-action="copy-citation"]').hidden = !navigator.clipboard?.writeText;
}).catch(() => {}); // The download remains available if loading fails.
document.addEventListener("click", async (e) => {
  const picker = $(".design-model-picker");
  if (picker?.open && !picker.contains(e.target)) picker.open = false;
  const b = e.target.closest("button,a[data-action]");
  if (b?.dataset.action === "copy-citation") {
    try {
      await navigator.clipboard.writeText(citationText);
      const label = b.querySelector("[data-citation-copy-label]");
      label.textContent = "Copied";
      clearTimeout(b.copyTimeout);
      b.copyTimeout = setTimeout(() => { label.textContent = "Copy BibTeX"; }, 2200);
    } catch {
      toast("Could not copy. Use Download to save the BibTeX file.");
    }
    return;
  }
  if (!b || !data) return;
  if (b.dataset.exploreTask) {
    state.exploreTask = b.dataset.exploreTask;
    renderExplorer();
    $(`[data-explore-task="${state.exploreTask}"]`)?.focus({preventScroll:true});
    return;
  }
  if (b.dataset.exploreMode) {
    state.exploreMode = b.dataset.exploreMode;
    renderExplorer();
    return;
  }
  if (b.dataset.designFocus) {
    state.designActive = b.dataset.designFocus;
    renderDesign(`[data-design-focus="${state.designActive}"]`);
    return;
  }
  if (b.dataset.action === "explore-in-table") {
    chooseTask(state.exploreTask);
    $("#leaderboard").scrollIntoView({behavior:"smooth",block:"start"});
    return;
  }
  if (b.dataset.focusTask) {
    if (state.sort === b.dataset.focusTask) {
      state.direction = state.direction === "higher" ? "lower" : "higher";
      render();
    } else chooseTask(b.dataset.focusTask);
    return;
  }
  if (b.dataset.sort) {
    const id = b.dataset.sort;
    if (state.sort === id)
      state.direction = state.direction === "higher" ? "lower" : "higher";
    else {
      state.sort = id;
      state.direction = lookup.tasks.get(id)?.direction || "higher";
    }
    render();
    return;
  }
  if (b.dataset.model) {
    openDialog("model", b.dataset.model);
    return;
  }
  if (b.dataset.task) {
    openDialog("task", b.dataset.task);
    return;
  }
  if (b.dataset.cell) {
    const [m, t] = b.dataset.cell.split(":");
    openDialog("cell", m, t);
    return;
  }
  if (b.dataset.reference) {
    openDialog("reference", b.dataset.reference);
    return;
  }
  if (b.dataset.taskCategory) {
    const id =
      state.dialog?.id ||
      data.tasks.find((t) => t.categoryId === b.dataset.taskCategory)?.id;
    closeDialog();
    chooseTask(id);
    $("#leaderboard").scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
    return;
  }
  const action = b.dataset.action;
  if (b.dataset.budget) {
    const focusedBudget = b.dataset.budget;
    $("#dialog-content .dialog-body").innerHTML = budgetExplorer(
      data,
      Number(focusedBudget),
    );
    document
      .querySelector(`[data-budget="${focusedBudget}"]`)
      .focus({ preventScroll: true });
    return;
  }
  if (
    [
      "method",
      "score",
      "sources",
      "submission",
      "references",
      "budget",
    ].includes(action)
  ) {
    openDialog(action);
    return;
  }
  if (action === "close") {
    closeDialog();
    return;
  }
  if (action === "scroll-table") {
    const wrapper = $("#table-wrapper");
    const maximum = wrapper.scrollWidth - wrapper.clientWidth;
    wrapper.scrollTo({left: wrapper.scrollLeft < maximum - 2 ? maximum : 0, behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth"});
    return;
  }
  if (action === "baselines") {
    state.baselines = !state.baselines;
    const rows = $("#baseline-rows");
    rows.classList.toggle("is-expanded", state.baselines);
    rows.inert = !state.baselines;
    rows.setAttribute("aria-hidden", String(!state.baselines));
    b.setAttribute("aria-expanded", String(state.baselines));
    syncURL();
    return;
  }
  if (action === "download") {
    downloadRows(
      [
        ...sortedModels(filteredModels()),
        ...(state.baselines ? sortedModels(filteredModels(true)) : []),
      ],
      visibleTasks(),
      "bend2-results.csv",
    );
    return;
  }
  if (action === "download-all") {
    downloadRows(data.models, data.tasks, "bend2-all-results.csv");
    return;
  }
  if (action === "share") {
    syncURL();
    try {
      await navigator.clipboard.writeText(location.href);
      toast("Link copied.");
    } catch {
      toast("Copy the current address to share this view.");
    }
    return;
  }
});
document.addEventListener("change", (e) => {
  if (e.target.matches("[data-design-model]")) {
    const id = e.target.dataset.designModel;
    if (e.target.checked && state.designModels.length < 3) state.designModels.push(id);
    else state.designModels = state.designModels.filter(m => m !== id);
    const designReferences = data.supplementary?.repairBudgets?.experimentalReference ? ["uniform", "experimental_reference"] : ["uniform"];
    if (![...state.designModels, ...designReferences].includes(state.designActive)) state.designActive = state.designModels[0] || "uniform";
    renderDesign(`[data-design-model="${id}"]`);
    return;
  }

});
function highlightModel(id) {
  document
    .querySelectorAll("[data-summary-model],[data-row]")
    .forEach((el) =>
      el.classList.toggle(
        "is-highlighted",
        Boolean(id) && (el.dataset.summaryModel || el.dataset.row) === id,
      ),
    );
}
document.addEventListener("pointerover", (e) => {
  const el = e.target.closest("[data-summary-model],[data-row]");
  if (el && !el.contains(e.relatedTarget))
    highlightModel(el.dataset.summaryModel || el.dataset.row);
});
document.addEventListener("pointerout", (e) => {
  const el = e.target.closest("[data-summary-model],[data-row]");
  if (el && !el.contains(e.relatedTarget)) highlightModel(null);
});
document.addEventListener("focusin", (e) => {
  const el = e.target.closest("[data-summary-model],[data-row]");
  if (el) highlightModel(el.dataset.summaryModel || el.dataset.row);
});
document.addEventListener("focusout", (e) => {
  e.target.removeAttribute?.("data-pointer-return");
  highlightModel(null);
});
document.addEventListener("keydown", (e) => {
  document.querySelector("[data-pointer-return]")?.removeAttribute("data-pointer-return");
  const picker = $(".design-model-picker");
  if (e.key === "Escape" && picker?.open && !$("#detail-dialog").open) {
    e.preventDefault();
    picker.open = false;
    picker.querySelector("summary").focus({preventScroll:true});
    return;
  }
});
$("#detail-dialog").addEventListener("cancel", (e) => {
  e.preventDefault();
  closeDialog();
});
$("#detail-dialog").addEventListener("click", (e) => {
  if (e.target === $("#detail-dialog")) {
    const r = e.target.getBoundingClientRect();
    if (
      e.clientX < r.left ||
      e.clientX > r.right ||
      e.clientY < r.top ||
      e.clientY > r.bottom
    )
      closeDialog();
  }
});
window.addEventListener("popstate", () => {
  // A chapter jump does not change results or require replacing the charts.
  if (location.search === renderedSearch) return;
  readURL();
  render();
  renderExplorer();
  renderDesign();
  if (state.dialog) openDialog(state.dialog.type, state.dialog.id);
  else if ($("#detail-dialog").open) $("#detail-dialog").close();
});
const tableOverflowState = { more:null, overflow:null, scrolled:null };
function updateTableOverflow() {
  const wrapper = $("#table-wrapper"), frame = $(".table-frame"), cue = $("#table-scroll-cue");
  if (!wrapper || !frame || !cue) return;
  const maximum = wrapper.scrollWidth - wrapper.clientWidth;
  const overflow = maximum > 2, more = overflow && wrapper.scrollLeft < maximum - 2;
  const scrolled = wrapper.scrollLeft > 2;
  if (more !== tableOverflowState.more) {
    frame.classList.toggle("has-more-columns", more);
    cue.innerHTML = more ? '<span class="cue-label">More tasks</span><span aria-hidden="true">→</span>' : '<span aria-hidden="true">←</span><span class="cue-label">First tasks</span>';
    cue.setAttribute("aria-label", more ? "Scroll to later tasks" : "Scroll to earlier tasks");
    tableOverflowState.more = more;
  }
  if (overflow !== tableOverflowState.overflow) {
    frame.classList.toggle("has-horizontal-overflow", overflow);
    cue.hidden = !overflow;
    tableOverflowState.overflow = overflow;
  }
  if (scrolled !== tableOverflowState.scrolled) {
    frame.classList.toggle("is-scrolled", scrolled);
    tableOverflowState.scrolled = scrolled;
  }
}
$("#table-wrapper").addEventListener("scroll", updateTableOverflow, {passive:true});
window.addEventListener("resize", updateTableOverflow);
async function init() {
  try {
    initPageNavigation({ updateTableOverflow });
    const response = await fetch("./data/benchmark.json");
    if (!response.ok) throw new Error(`Data returned ${response.status}`);
    data = await response.json();
    lookup = indexData(data);
    initOverview(data);
    readURL();
    $('[data-action="download"]').innerHTML = icon("download", 17);
    renderExplorer();
    renderDesign();
    $("#dataset-links").innerHTML = data.datasets.filter(dataset => dataset.url?.startsWith("https://")).map(dataset => `<a href="${escape(dataset.url)}" target="_blank" rel="noopener noreferrer">${escape(dataset.shortLabel)} <span aria-hidden="true">↗</span></a>`).join("");
    render();
    let compactDesign = $("#design-content").clientWidth < 600;
    new ResizeObserver(() => {
      const next = $("#design-content").clientWidth < 600;
      if (next !== compactDesign) { compactDesign = next; renderDesign(); }
    }).observe($("#design-content"));
    if (state.dialog) openDialog(state.dialog.type, state.dialog.id);
  } catch (error) {
    console.error(error);
    $("#table-wrapper").innerHTML =
      '<div class="error-state"><h3>The results could not be loaded.</h3><p>Please refresh the page, or download the benchmark data directly.</p><a href="./data/benchmark.json">Benchmark data ↗</a></div>';
  }
}
init();
