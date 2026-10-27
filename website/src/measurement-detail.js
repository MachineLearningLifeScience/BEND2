import { finite, taskScore } from "./scoring.js";

const escape = (value) => String(value ?? "").replace(
  /[&<>"']/g,
  (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character],
);
const format = (value, precision = 3) => finite(value)
  ? value.toFixed(precision).replace("-", "−") : "—";

const metrics = {
  prior: "Hidden-base loss · bits/base",
  opensplice: "Macro-gene Spearman correlation",
  context: "Macro-element Spearman correlation",
  tissue_identification: "Correct tissue · %",
  background: "Macro-element Spearman correlation",
  repair_percentile: "Measured residual rank · percentile",
  cell_selective: "Selection utility · log₂",
  atlas_profile: "Gain over random · log₂",
};

const taskDescriptions = {
  prior: "Predict a hidden base from its surrounding DNA.",
  opensplice: "Predict how a mutation changes alternative splicing.",
  context: "Predict how a mutation’s effect differs between HepG2 and K562.",
  tissue_identification: "Match a predicted expression profile to the correct tissue among 51 candidates.",
  background: "Predict how the same mutation’s effect differs between two genetic backgrounds.",
  repair_percentile: "Choose a single-base edit with an effect as close as possible to the reference edit.",
  cell_selective: "Choose an edit, or no edit, to increase activity in one cell type while limiting its effect in the other.",
  atlas_profile: "Choose ten enhancers that are active in the requested cell types and inactive in the others.",
};

export const taskSummary = (task) => taskDescriptions[task.id] || task.description;

const referenceDescriptions = {
  opensplice: "Agreement between repeated RNA measurements of mutation effects, averaged within genes.",
  context: "Agreement between cell-type contrasts estimated from separate groups of RNA and DNA measurements.",
  tissue_identification: "Identify each tissue using expression profiles from separate donor halves, averaging both directions.",
  background: "Agreement between measured background interactions in HepG2 and K562, averaged within regulatory elements.",
  repair_percentile: "Choose edits using one group of experimental measurements and evaluate their ranks using the other, averaging both directions.",
  cell_selective: "Choose cell-selective edits using one group of RNA measurements and evaluate their utility using the other, averaging both directions.",
  atlas_profile: "Choose ten enhancers using one RNA measurement and evaluate their gain using the other, averaging both directions across sixteen requests.",
};

function readoutLabel(model, task, measured) {
  if (task.id === "prior") {
    if (measured) return "Sequence probabilities";
    return model.interface === "native" ? "Native-output configuration" : "Prior evaluation";
  }
  if (model.interface === "native")
    return task.id === "atlas_profile" ? "Head fitted to native outputs" : "Native outputs";
  if (model.interface === "fitted")
    return model.kind === "foundation" ? "Embedding-fitted linear head" : "Fitted sequence features";
  return model.interface === "sequence" ? "Sequence baseline" : "Task-trained model";
}

function context(data, taskId) {
  const task = data.tasks.find((item) => item.id === taskId);
  if (!task) throw new RangeError(`Unknown benchmark task: ${taskId}`);
  return {
    task,
    category: data.categories.find((item) => item.id === task.categoryId),
    dataset: data.datasets.find((item) => item.id === task.datasetId),
  };
}

function repeatData(data, modelId, taskId) {
  const cell = data.measurements.find(item => item.modelId === modelId && item.taskId === taskId);
  if (taskId === "atlas_profile" && cell?.replicateValues) return { repeatValues: cell.replicateValues };
  return taskId === "atlas_profile"
    ? data.supplementary?.multiCellRepeats?.points?.find((item) => item.modelId === modelId)
    : null;
}

function resultMarkup(task, cell) {
  const measured = finite(cell?.value);
  const status = cell?.status === "unsupported"
    ? "Not applicable to this interface" : cell?.status === "not_evaluated"
      ? (cell.notes?.[0] || "Not evaluated in this submission") : "Result not available in this snapshot";
  const uncertainty = measured && cell.uncertainty;
  const interval = uncertainty
    ? ` · ${format(100 * uncertainty.level, 0)}% interval ${format(uncertainty.low, task.precision)}–${format(uncertainty.high, task.precision)}` : "";
  return `${cell?.verification ? `<p class="measurement-verification">${escape(cell.verification.label)}</p>` : ""}<div class="measurement-result${measured ? "" : " is-missing"}"><span class="measurement-value">${escape(cell?.displayValue || "—")}</span><div class="measurement-metric"><span>${escape(metrics[task.id] || task.metric)}</span><small>${measured ? `${task.direction === "lower" ? "Lower" : "Higher"} is better${interval}` : escape(status)}</small></div></div>`;
}

function repeatMarkup(task, cell, repeats) {
  const repeatValues = finite(cell?.value) ? (repeats?.repeatValues || []).filter(finite) : [];
  const absolute = finite(repeats?.absoluteUtility)
    ? `<p>Absolute utility: ${format(repeats.absoluteUtility, 3)}. The reported gain subtracts intent-matched random selection.</p>` : "";
  return `${repeatValues.length ? `<div class="measurement-repeats"><dl>${repeatValues.map((value, index) => `<div><dt>RNA measurement ${index + 1}</dt><dd>${format(value, task.precision)}</dd></div>`).join("")}</dl><p>Repeat measurements, not confidence intervals.</p></div>` : ""}${absolute}`;
}

function sourceMarkup(data, cell, task) {
  const contribution = data.sources?.find((item) => item.id === cell?.sourceId && item.submissionPath);
  if (contribution) {
    let evidenceURL = "";
    try { if (new URL(contribution.url).protocol === "https:") evidenceURL = contribution.url; } catch {}
    const recordURL = /^submissions\/community-[a-z0-9-]+\.json$/.test(contribution.submissionPath)
      ? `https://github.com/yhsure/genomic-bending/blob/benchmark/${contribution.submissionPath}` : "";
    const reviewURL = /^reviews\/community-[a-z0-9-]+\.json$/.test(contribution.reviewPath || "")
      ? `https://github.com/yhsure/genomic-bending/blob/benchmark/${contribution.reviewPath}` : "";
    const audit = cell?.verification?.reproduction;
    let rerunURL = "";
    try { if (new URL(audit?.evidence?.url).protocol === "https:") rerunURL = audit.evidence.url; } catch {}
    const missing = cell?.status === "not_evaluated";
    const label = missing ? "Not evaluated" : (cell?.verification?.label || "Community submission");
    const explanation = missing
      ? "No score was submitted for this task. The linked evidence covers this model's evaluated tasks."
      : cell?.verification?.rescored
      ? "Maintainers checked predictions, decisions and scores against benchmark labels."
      : "This submission is awaiting maintainer review.";
    const reproduction = audit
      ? `<p>Independently rerun by ${escape(audit.reviewer)}. Rerun estimate: <code>${escape(audit.metric.value)}</code>. ${escape(audit.notes)}${rerunURL ? ` <a href="${escape(rerunURL)}" target="_blank" rel="noopener noreferrer">Rerun evidence ↗</a>` : ""}</p>`
      : (cell?.verification?.rescored ? "<p>BEND has not independently rerun the model for this task.</p>" : "");
    return `<div class="measurement-source"><p>${escape(label)}</p><p>${explanation}</p>${reproduction}${reviewURL ? `<p><a href="${escape(reviewURL)}" target="_blank" rel="noopener noreferrer">Review record ↗</a></p>` : ""}<p>Protocol <code>${escape(contribution.protocolVersion)}</code>${cell?.sourceRecordId ? ` · <code>${escape(cell.sourceRecordId)}</code>` : ""}</p>${finite(cell?.sourceValue) ? `<p>Source estimate: <code>${escape(cell.sourceValue)}</code>. Display and ranking use the same precision as the paper rows.</p>` : ""}<p>${evidenceURL ? `<a href="${escape(evidenceURL)}" target="_blank" rel="noopener noreferrer">Download evaluation evidence ↓</a>` : ""}${recordURL ? ` · <a href="${escape(recordURL)}" target="_blank" rel="noopener noreferrer">Submission record ↗</a>` : ""}</p><p>Evidence SHA256: <code>${escape(contribution.sha256)}</code></p></div>`;
  }
  const source = data.sources?.find((item) => item.id === "table-1-records");
  const path = /^provenance\/[a-z0-9_./-]+$/i.test(source?.snapshotPath || "")
    ? source.snapshotPath : "provenance/table-1-source-records.csv";
  const shared = cell?.sharedFrom ? "<p>Website addition: this is the same checkpoint-level sequence-prior evaluation reported for the fitted-head row. It uses the model’s nucleotide probabilities and requires no fitted head or new inference.</p>" : "";
  const diagnostic = data.sources?.find(item => item.id === cell?.diagnosticSourceId);
  const diagnosticLink = diagnostic && /^provenance\/[a-z0-9_./-]+$/i.test(diagnostic.snapshotPath)
    ? `<p><a href="./${escape(diagnostic.snapshotPath)}">Read the query audit</a></p>` : "";
  return `<div class="measurement-source">${shared}${diagnosticLink}<p>Manuscript Table 1 · ${escape(task.figure)}<br>Snapshot <code>${escape(data.source?.commit?.slice(0, 8) || "")}</code>${cell?.sourceRecordId ? ` · <code>${escape(cell.sourceRecordId)}</code>` : ""}</p>${finite(cell?.sourceValue) ? `<p>Source estimate: <code>${escape(cell.sourceValue)}</code>. The result above uses manuscript precision.</p>` : ""}<a href="./${escape(path)}" download>Download source records ↓</a></div>`;
}

function methodMarkup(data, model, task, dataset, cell, repeats) {
  const measured = finite(cell.value);
  const normalized = measured ? taskScore(data, model.id, task.id) : null;
  const anchor = data.measurements.find((item) => item.modelId === data.scoring.referenceModelId && item.taskId === task.id);
  const inAggregate = data.scoring.defaultTaskIds.includes(task.id);
  const readout = measured && cell.interface
    ? `<div><dt>Readout</dt><dd>${escape(cell.interface)}</dd></div>` : "";
  const sampling = measured && cell.uncertainty
    ? `<div><dt>Uncertainty</dt><dd>Reported pointwise ${format(100 * cell.uncertainty.level, 0)}% bootstrap interval; resampling unit: ${escape(cell.uncertainty.samplingUnit)}.</dd></div>` : "";
  const normalizedMarkup = measured && inAggregate && finite(normalized)
    ? `<p class="measurement-normalization">Fixed-reference task score: <strong>${format(normalized, 1)}</strong>. Baseline ${format(task.baseline.value, task.precision)}; NTv3 650M post ${format(anchor?.value, task.precision)}. <button data-action="score">Scoring definition ↗</button></p>`
    : "";
  const interfaceNote = measured && task.id === "cell_selective" && model.interface === "native"
    ? "<p>Native outputs use held-locus calibration.</p>" : "";
  return `<details class="measurement-method"><summary>Method and source</summary><div class="measurement-method-content"><p>${escape(task.description)}</p><dl><div><dt>Dataset</dt><dd>${escape(dataset?.shortLabel || dataset?.label || task.datasetId)}</dd></div><div><dt>Cohort</dt><dd>${escape(task.cohort)}</dd></div>${readout}${sampling}</dl>${interfaceNote}${repeatMarkup(task, cell, repeats)}${normalizedMarkup}${sourceMarkup(data, cell, task)}</div></details>`;
}

/** A compact result explanation for the existing dialog frame. */
export function measurementDetail(data, modelId, taskId) {
  const { task, category, dataset } = context(data, taskId);
  const model = data.models.find((item) => item.id === modelId);
  if (!model) throw new RangeError(`Unknown benchmark model: ${modelId}`);
  const cell = data.measurements.find((item) => item.modelId === modelId && item.taskId === taskId);
  if (!cell) throw new RangeError(`No benchmark record: ${modelId}/${taskId}`);
  const measured = finite(cell.value);
  const repeats = repeatData(data, modelId, taskId);
  return {
    title: task.label,
    eyebrow: `${model.label.replace(/ · native$/, "")} · ${readoutLabel(model, task, measured)}`,
    body: `<div class="measurement-detail" style="--measurement-color:${escape(category?.color || "#315a49")}" data-measurement="${escape(modelId)}:${escape(taskId)}" data-status="${escape(cell.status)}">${resultMarkup(task, cell)}<p class="measurement-explanation">${escape(!measured && cell.missingReason ? cell.missingReason : taskDescriptions[taskId] || task.description)}</p><button class="measurement-task-link" data-task="${escape(taskId)}">Compare models</button>${methodMarkup(data, model, task, dataset, cell, repeats)}</div>`,
  };
}

/** Experimental references use the same hierarchy, without model normalization. */
export function referenceDetail(data, taskId) {
  const { task, dataset } = context(data, taskId);
  const reference = data.references.find((item) => item.taskId === taskId);
  if (!reference) throw new RangeError(`No experimental reference: ${taskId}`);
  const repeats = repeatData(data, "experimental_reference", taskId);
  const cohort = taskId === "context"
    ? "127 regulatory elements with physical count measurements"
    : task.cohort.split(";")[0];
  const protocolNotes = taskId === "atlas_profile"
    ? "The same sixteen programs and ten nominations are evaluated in both directions. Gain is measured relative to intent-matched random selection."
    : reference.caveat;
  return {
    title: task.label,
    eyebrow: taskId === "background" ? "HepG2–K562 transfer" : "Experimental reference",
    body: `<div class="measurement-detail measurement-reference" style="--measurement-color:#77766f" data-measurement="experimental_reference:${escape(taskId)}" data-status="${escape(reference.status)}">${resultMarkup(task, reference)}<p class="measurement-explanation">${escape(referenceDescriptions[taskId] || task.description)}</p><button class="measurement-task-link" data-task="${escape(taskId)}">Compare models</button><details class="measurement-method"><summary>Method and source</summary><div class="measurement-method-content"><dl><div><dt>Dataset</dt><dd>${escape(dataset?.shortLabel || dataset?.label || task.datasetId)}</dd></div><div><dt>Cohort</dt><dd>${escape(cohort)}</dd></div><div><dt>Readout</dt><dd>${escape(reference.interface)}</dd></div>${reference.uncertainty ? `<div><dt>Uncertainty</dt><dd>Reported pointwise ${format(reference.uncertainty.level * 100, 0)}% bootstrap interval; resampling unit: ${escape(reference.uncertainty.samplingUnit)}.</dd></div>` : ""}</dl><p>${escape(protocolNotes)}</p>${repeatMarkup(task, reference, repeats)}<p>Experimental references provide comparisons, not performance ceilings. They do not enter the combined-score normalization.</p>${sourceMarkup(data, reference, task)}</div></details></div>`,
  };
}
