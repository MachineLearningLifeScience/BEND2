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
import { budgetExplorer } from "./budget.js";
import { explorerRows, taskExplorerChart } from "./explore-charts.js";
import { pairedChart } from "./paired-chart.js";
import { designExplorer, DEFAULT_DESIGN_MODELS } from "./design-explorer.js";
import { measurementDetail, referenceDetail } from "./measurement-detail.js";
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
const refDescriptions = {
  opensplice:
    "Agreement between RNA repeat measurements of mutation effects, with the wild-type PSI shared between repeats.",
  context:
    "Agreement between cell contrasts reconstructed from disjoint experimental repeat subsets.",
  tissue_identification:
    "Tissue identification between two donor halves, averaged over both directions.",
  background:
    "HepG2–K562 transfer: agreement of measured background interactions across the two cell types.",
  repair_percentile:
    "Choose edits using one set of experimental repeats; evaluate their measured ranks on the other set. Average both directions.",
  cell_selective:
    "Choose edits using one set of RNA repeats and evaluate utility on the other. Average both directions.",
  atlas_profile:
    "Choose ten enhancers on one RNA repeat and evaluate on the other. Average both directions.",
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
  ? `https://github.com/yhsure/genomic-bending/blob/benchmark/${path}` : "";
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
  // Retired search and readout parameters must not silently hide model rows.
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
    .map((m) => raw(m.id, task.id))
    .filter(finite);
  const lo = Math.min(task.baseline.value, ...values),
    hi = Math.max(task.baseline.value, ...values);
  const f =
    hi === lo
      ? 0.5
      : task.direction === "higher"
        ? (value - lo) / (hi - lo)
        : (hi - value) / (hi - lo);
  const amount = 0.025 + 0.16 * Math.pow(Math.max(0, Math.min(1, f)), 1.6);
  const h = colorFor(task);
  return `rgba(${parseInt(h.slice(1, 3), 16)},${parseInt(h.slice(3, 5), 16)},${parseInt(h.slice(5, 7), 16)},${amount})`;
}
function metricButton(model, task) {
  const m = getCell(model.id, task.id),
    missing = !finite(m?.value),
    special = task.id === "atlas_profile" && model.interface === "native";
  const title = (missing
    ? m?.status === "unsupported"
      ? "Not applicable to this interface"
      : m?.status === "not_evaluated" ? (m.notes?.[0] || "Not evaluated in this submission") : "Result not available"
    : m.uncertainty
      ? `95% interval: ${fmt(m.uncertainty.low, task.precision)}–${fmt(m.uncertainty.high, task.precision)}. Click for details.`
      : "Click for the evaluation setting and source.") + (special && !missing ? " Fitted head using native-output features." : "");
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
  const maxIndex = Math.max(100, ...data.models.map(m => overallScore(data,m.id)).filter(finite));
  const combinedCell = (m) => {
    const score = overallScore(data,m.id), cov = scoreCoverage(data,m.id);
    const partial = cov.tasks.complete < cov.tasks.total;
    const description = `${partial ? 'Partial' : 'Combined'} score: ${fmt(score)}; ${cov.tasks.complete} of ${cov.tasks.total} tasks, ${cov.categories.complete} of ${cov.categories.total} categories`;
    return `<td class="index-cell" title="${description}"><button class="index-score" data-action="score" aria-label="${escape(m.label)}, ${description}">${fmt(score)}</button>${finite(score) ? `<div class="index-bar" aria-hidden="true"><i style="width:${Math.max(0,100*score/maxIndex)}%"></i></div>` : ''}</td>`;
  };
  let html = `<table class="results-table" aria-label="BEND 2.0 benchmark results" style="--active-category:${colorFor(task)}"><colgroup><col class="model-col"><col class="index-col">${tasks.map(t => `<col class="score-col ${t.id === state.sort ? "active-task" : ""}">`).join("")}</colgroup><thead><tr class="group-row"><th></th><th class="index-group">Overall</th>${data.categories.map((c) => `<th class="group" colspan="${tasks.filter((t) => t.categoryId === c.id).length}" scope="colgroup" style="--category:${c.color}">${shortCategories[c.id]}</th>`).join("")}</tr><tr class="task-row"><th class="model-header" aria-sort="${state.sort === "name" ? (state.direction === "higher" ? "ascending" : "descending") : "none"}"><div class="model-heading"><span class="rank-heading" title="${escape(rankLabel)} ranking">Rank</span><button data-sort="name" aria-label="Sort by model name">Model / readout ${state.sort === "name" ? `<span class="heading-arrow" aria-hidden="true">${state.direction === "higher" ? "↓" : "↑"}</span>` : ""}</button></div></th><th class="index-heading ${state.sort === "index" ? "active-task" : ""}" style="--category:var(--forest)" aria-sort="${state.sort === "index" ? (state.direction === "higher" ? "descending" : "ascending") : "none"}"><button class="task-label" data-sort="index" aria-label="Sort by combined score">Combined<br>score ${state.sort === "index" ? `<span class="heading-arrow" aria-hidden="true">${state.direction === "higher" ? "↓" : "↑"}</span>` : ""}</button><div class="heading-meta"><span>100 = NTv3 ref.</span><button class="task-info" data-action="score" aria-label="About the combined score" title="Combined score definition">${icon("info",12)}</button></div></th>${tasks.map((t) => `<th scope="col" class="metric-heading ${state.sort === t.id ? "active-task" : ""}" style="--category:${colorFor(t)}" aria-sort="${state.sort === t.id ? (state.direction === "higher" ? "descending" : "ascending") : "none"}"><button class="task-label" data-focus-task="${t.id}" aria-pressed="${state.sort === t.id}" aria-label="Sort by ${escape(t.label)}">${headings[t.id].map((label,i) => `${label}${i === headings[t.id].length-1 && state.sort === t.id ? `<span class="heading-arrow" aria-hidden="true">${state.direction === "higher" ? "↓" : "↑"}</span>` : ""}`).join("<br>")}</button><div class="heading-meta"><span>${conciseUnits[t.id]}</span><button class="task-info" data-task="${t.id}" aria-label="About ${escape(t.label)}" title="Task definition">${icon("info",12)}</button></div></th>`).join("")}</tr></thead><tbody>`;
  const row = (m) => `<tr data-row="${m.id}"><td class="model-cell"><div class="model-identity">${rankMark(m)}<div class="model-description"><button class="model-name" data-model="${m.id}" aria-label="${escape(modelTitle(m))} (${escape(readout(m))})">${escape(modelTitle(m))}</button><span class="model-sub" title="${escape(readout(m))}">${m.origin === "community" ? "Community · " : ""}${escape(readout(m))}</span></div></div></td>${combinedCell(m)}${tasks.map((t) => `<td class="metric-cell ${state.sort === t.id ? "active-task" : ""}">${metricButton(m, t)}</td>`).join("")}</tr>`;
  html += models.map(row).join("");
  html += `<tr class="contribution-row"><td colspan="${colCount}"><button class="add-model-button" data-action="submission"><span>＋ Add your model</span><span>Evaluate a task and submit your result ↗</span></button></td></tr>`;
  html += `<tr class="baseline-disclosure-row"><td colspan="${colCount}"><button id="baseline-toggle" class="baseline-disclosure" data-action="baselines" aria-expanded="${state.baselines}" aria-controls="baseline-rows"><span class="baseline-disclosure-label"><span class="disclosure-gutter" aria-hidden="true"><span class="disclosure-mark"></span></span><span>Baselines &amp; specialists</span></span></button></td></tr></tbody><tbody id="baseline-rows" class="${state.baselines ? "is-expanded" : ""}"${state.baselines ? "" : ' inert aria-hidden="true"'}>${base.map(row).join("")}</tbody><tbody>`;
  html += `<tr class="reference-row"><td class="model-cell"><div class="model-identity"><span class="model-rank-spacer" aria-hidden="true"></span><button class="model-name" data-action="references">Experimental reference</button></div></td><td class="index-cell">—</td>${tasks.map(t => {const r = data.references.find(r => r.taskId === t.id);return `<td class="metric-cell ${t.id === state.sort ? 'active-task' : ''}">${r ? `<button class="score-cell" data-reference="${t.id}" style="--tint:${tint(t,r.value)};--category:${colorFor(t)}" aria-label="${escape(t.label)} experimental reference ${r.displayValue}">${r.displayValue}</button>` : "—"}</td>`;}).join("")}</tr></tbody></table>`;
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
function dialogFrame(title, eyebrow, body) {
  return `<div class="dialog-head"><div><span class="eyebrow">${escape(eyebrow)}</span><h2 id="dialog-title">${escape(title)}</h2></div><button class="close-button" data-action="close" aria-label="Close dialog">${icon("close", 23)}</button></div><div class="dialog-body">${body}</div>`;
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
      "Response matching by testing budget",
      "Genomic design / Figure 5B",
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
  return dialogFrame("Combined score", "Eight tasks · five categories",
    `<div class="score-definition"><p class="dialog-lede">NTv3 650M post sets the reference at 100.</p>
    <p>Each task is normalized between its fixed baseline and NTv3 650M post:</p>
    <div class="score-formula" role="img" aria-label="100 times the result minus baseline, divided by the NTv3 reference minus baseline"><span>100 ×</span><span class="score-fraction"><span>result − baseline</span><span>NTv3 reference − baseline</span></span></div>
    <p>We average available task scores within each category, then give the available categories equal weight. The five categories are Sequence priors, Function, Context, Interactions and Design.</p>
    <p>Missing tasks are omitted, rather than counted as zero. Task and category counts are available on hover and in the CSV download. Scores can exceed 100 or fall below zero.</p>
    <p class="score-definition-note">This combined score is a proposed leaderboard measure; the individual task results come from the manuscript.</p></div>`);
}
function methodDialog() {
  return dialogFrame(
    "Reading the results",
    "Methods",
    `<p class="dialog-lede">Eight benchmark endpoints, with frozen paper results and reviewed community submissions.</p><p>Each column uses the task’s original units. Select its heading to sort the models.</p><h3>Readouts</h3><p><strong>Embedding heads</strong> are linear predictors fitted to frozen model representations. <strong>Native outputs</strong> use released functional predictions, with task-specific calibration. For multi-cell design, native outputs are used as features for a fitted head.</p><h3>Measurements</h3><p>Task details show reported 95% confidence intervals where available. Multi-cell RNA repeats are separate experimental measurements; their values are available in the task details.</p><p>Experimental references measure agreement or selection using experimental data. Each task has its own construction, described alongside the result.</p><details class="score-method"><summary>Combined score</summary><p>The combined score uses fixed baselines and NTv3 650M post as a reference. It is a website scoring proposal, not a paper result.</p><div class="method-equation">100 × (result − baseline) / (NTv3 reference − baseline)</div><p>Available task scores are averaged within each category, then available categories receive equal weight. Sequence priors are included. Missing tasks are omitted; task and category coverage is available on hover and in the CSV download. The scale is fixed to NTv3 650M post = 100.</p><table class="protocol-table"><thead><tr><th>Task</th><th>Baseline</th><th>NTv3 reference</th></tr></thead><tbody>${data.tasks.filter(t => data.scoring.defaultTaskIds.includes(t.id)).map((t) => `<tr><td>${escape(t.label)}</td><td>${fmt(t.baseline.value, t.precision)}</td><td>${fmt(raw(data.scoring.referenceModelId, t.id), t.precision)}</td></tr>`).join("")}</tbody></table></details><button class="text-action" data-action="sources">Data sources ↗</button>`,
  );
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
    readout(m),
    `${contribution}<p>${escape(m.description)}</p><p class="model-detail-line">${escape(m.parameterLabel || "Parameter count not specified")} · ${cov.complete} of ${cov.total} tasks evaluated</p><table class="model-score-table"><tbody>${data.tasks
      .map((t) => {
        const cell = getCell(id, t.id);
        return `<tr><td><button data-cell="${id}:${t.id}"><i class="category-dot" style="--category:${colorFor(t)}"></i>${escape(t.label)}</button></td><td>${escape(cell.displayValue)}</td><td>${conciseUnits[t.id]}</td></tr>`;
      })
      .join(
        "",
      )}</tbody></table>${m.interface === "native" && (finite(raw(id,"atlas_profile")) || finite(raw(id,"cell_selective"))) ? `<p class="model-detail-line">${finite(raw(id,"atlas_profile")) ? "Multi-cell results use a linear head fitted to native outputs. " : ""}${finite(raw(id,"cell_selective")) ? "Cell-selective results include held-locus calibration." : ""}</p>` : ""}`,
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
    `${cat.label} / ${t.figure}`,
    `<p class="dialog-lede">${escape(t.description)}</p><div class="detail-tags"><span>${escape(ds?.label || ds?.name || t.datasetId)}</span><span>${escape(t.metric)}</span><span>${t.direction === "higher" ? "Higher" : "Lower"} is better</span></div><p>${escape(t.cohort)}</p>${id === "repair_percentile" ? '<button class="dark-button" data-action="budget">Results by testing budget →</button>' : ""}<div class="task-chart"><div class="chart-axis"><span>${fmt(min, min < 0 ? 1 : 0)}</span><span>${fmt((min + max) / 2, 2)}</span><span>${fmt(max, 2)}</span></div>${chartEntries.map((r) => chartRow(r.model, r.cell, r.kind)).join("")}</div><p class="chart-note">${id === "atlas_profile" ? "The two small markers show RNA measurement repeats 1 and 2. They are not confidence intervals." : "Black whiskers show reported 95% intervals. Gray rows are experimental references or baselines."} Select a row for its exact result and evaluation details.</p>${t.cautions?.length ? `<div class="method-note">${escape(t.cautions.filter((c) => !c.includes("superseded") && !c.includes("Original confirmatory")).join(" "))}</div>` : ""}<button class="text-action" data-task-category="${t.categoryId}" style="margin-top:20px">See ${cat.label.toLowerCase()} in the table ${icon("arrow", 14)}</button>`,
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
  return dialogFrame(
    "Experimental references",
    "Measurements alongside predictions",
    `<p class="dialog-lede">Experimental comparisons based on repeated measurements.</p><p>The gray row contains a task-specific comparison based on measured data. These are not a uniform performance ceiling.</p>${data.tasks
      .filter((t) => t.reference)
      .map(
        (t) =>
          `<h3><button data-reference="${t.id}" style="font:inherit;padding:0;text-align:left">${escape(t.label)} <span style="color:var(--muted)">${t.reference.value.toFixed(t.precision)}</span></button></h3><p>${escape(refDescriptions[t.id])}</p>`,
      )
      .join("")}`,
  );
}
function sourcesDialog() {
  return dialogFrame(
    "Data sources",
    "Data & provenance",
    `<p class="dialog-lede">This release reproduces the current manuscript’s Table 1.</p><p>Displayed values match the manuscript table precision. The original source estimates and available uncertainty intervals are retained in the downloadable records.</p><div class="source-box">Manuscript snapshot: <code>${data.source.commit}</code><br>Extracted: ${data.source.extractedOn}<br>Table SHA-256: <code>${data.source.tableSha256}</code></div><table class="protocol-table"><tbody>${data.sources
      .filter((s) => s.snapshotPath)
      .map(
        (s) =>
          `<tr><td>${escape(s.title)}</td><td><a href="./${escape(s.snapshotPath)}" download>Download ↗</a></td></tr>`,
      )
      .join(
        "",
      )}</tbody></table><p>Model results and experimental references are transcribed from the matched manuscript records; the underlying model evaluations have not been rerun for this website.</p><p><a href="./data/benchmark.json" download>Complete machine-readable benchmark</a> · <a href="./data/sources.md">Source and protocol notes</a></p><h3>Combined score definition</h3><p>The proposed reference index uses fixed anchors and category weights recorded in the dataset.</p>`,
  );
}
function submissionDialog() {
  return dialogFrame(
    "Add your model",
    "Leaderboard contribution",
    `<p class="dialog-lede">Connect your DNA model, evaluate a task, and submit the result for review. Any subset of tasks is welcome.</p>
    <h3>1. Evaluate your model</h3>
    <p>Follow the <a href="https://github.com/yhsure/genomic-bending/blob/benchmark/docs/quickstart.md" target="_blank" rel="noopener noreferrer">quickstart</a> to install BEND and create your adapter. Start with Atlas: its short sequences and frozen data are included.</p>
    <pre><code>bend2 plan my_model.py --tasks atlas_profile
bend2 run my_model.py --tasks atlas_profile --output results/my-model
bend2 show results/my-model</code></pre>
    <h3>2. Submit for review</h3>
    <p>With GitHub CLI installed and authenticated, choose a public model or results repository you can write to:</p>
    <pre><code>bend2 submit results/my-model --github your-lab/your-model</code></pre>
    <p>This publishes an evidence ZIP as a release asset in your repository and opens a pull request containing one generated JSON file in BEND. The evidence includes predictions and protocol details; model weights and embedding caches remain local. A maintainer reviews the model declaration and evidence. Merging the PR adds your row on the next website build; unrun tasks stay missing.</p>
    <div class="participate-actions"><a class="dark-button" style="color:var(--paper)" href="https://github.com/yhsure/genomic-bending/blob/benchmark/docs/submitting.md" target="_blank" rel="noopener noreferrer">Submission guide ↗</a><a href="https://github.com/yhsure/genomic-bending/tree/benchmark/submissions" target="_blank" rel="noopener noreferrer">Reviewed submissions ↗</a></div>
    <p>Other hosting works too: export the evidence, then use <code>bend2 submit --evidence-url</code> and open the one-file PR manually. Or <a href="https://github.com/yhsure/genomic-bending/issues/new?template=model.yml" target="_blank" rel="noopener noreferrer">send the generated JSON and evidence link in a submission issue</a> for maintainer help.</p>`,
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
        return [c.value, c.status, c.uncertainty?.low, c.uncertainty?.high];
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
