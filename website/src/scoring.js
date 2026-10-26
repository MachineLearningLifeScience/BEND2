/** Fixed-reference arithmetic scoring. Missing measurements never count as zero. */
export function finite(value) {
  return typeof value === "number" && Number.isFinite(value);
}
export function normalized(value, baseline, reference) {
  if (
    ![value, baseline, reference].every(finite) ||
    Math.abs(reference - baseline) < 1e-12
  )
    return null;
  return (100 * (value - baseline)) / (reference - baseline);
}
export function meanComplete(values) {
  return values.length && values.every(finite)
    ? values.reduce((a, b) => a + b, 0) / values.length
    : null;
}
export function meanAvailable(values) {
  return meanComplete(values.filter(finite));
}
export function indexData(data) {
  const tasks = new Map(data.tasks.map((t) => [t.id, t]));
  const models = new Map(data.models.map((m) => [m.id, m]));
  const measurements = new Map(
    data.measurements.map((m) => [`${m.modelId}:${m.taskId}`, m]),
  );
  return { tasks, models, measurements };
}
export function metric(data, modelId, taskId) {
  return (
    data.measurements.find((m) => m.modelId === modelId && m.taskId === taskId)
      ?.value ?? null
  );
}
export function taskScore(data, modelId, taskId) {
  const task = data.tasks.find((t) => t.id === taskId);
  return task
    ? normalized(
        metric(data, modelId, taskId),
        task.baseline.value,
        metric(data, data.scoring.referenceModelId, taskId),
      )
    : null;
}
export function categoryScore(data, modelId, categoryId) {
  return meanAvailable(
    data.tasks
      .filter((t) => t.categoryId === categoryId)
      .map((t) => taskScore(data, modelId, t.id)),
  );
}
export function overallScore(data, modelId, includePrior = true) {
  const categories = data.categories.filter(
    (c) => includePrior || c.id !== "priors",
  );
  return meanAvailable(
    categories.map((c) => categoryScore(data, modelId, c.id)),
  );
}
export function scoreCoverage(data, modelId, includePrior = true) {
  const categories = data.categories.filter((c) => includePrior || c.id !== "priors");
  const tasks = data.tasks.filter((t) => categories.some((c) => c.id === t.categoryId));
  return {
    tasks: { complete: tasks.filter((t) => finite(taskScore(data, modelId, t.id))).length, total: tasks.length },
    categories: { complete: categories.filter((c) => finite(categoryScore(data, modelId, c.id))).length, total: categories.length },
  };
}
export function coverage(data, modelId, taskIds = data.tasks.map((t) => t.id)) {
  return {
    complete: taskIds.filter((t) => finite(metric(data, modelId, t))).length,
    total: taskIds.length,
  };
}
export function ordered(items, valueFor, direction = "higher") {
  return [...items].sort((a, b) => {
    const x = valueFor(a),
      y = valueFor(b);
    if (!finite(x) && !finite(y))
      return a.sortOrder - b.sortOrder || a.label.localeCompare(b.label);
    if (!finite(x)) return 1;
    if (!finite(y)) return -1;
    return (
      (direction === "higher" ? y - x : x - y) ||
      a.sortOrder - b.sortOrder ||
      a.label.localeCompare(b.label)
    );
  });
}
export function ranks(items, valueFor, direction = "higher") {
  const map = new Map();
  let previous = null,
    rank = 0;
  ordered(items, valueFor, direction).forEach((m, i) => {
    const value = valueFor(m);
    if (!finite(value)) return;
    if (previous === null || Math.abs(value - previous) > 1e-9) rank = i + 1;
    map.set(m.id, rank);
    previous = value;
  });
  return map;
}
export function csvCell(value) {
  const text = String(value ?? "");
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}
