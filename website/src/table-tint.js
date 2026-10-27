import { finite } from "./scoring.js";

export function tableTintOpacity(task, value, modelValues) {
  if (!finite(value)) return 0;
  const baseline = task.baseline.value;
  const values = modelValues.filter(finite);
  const best = task.direction === "lower"
    ? Math.min(baseline, ...values)
    : Math.max(baseline, ...values);
  // Worse-than-baseline outliers must not deepen the colour of other results.
  const improvement = best === baseline ? 0 : (value - baseline) / (best - baseline);
  return .025 + .16 * Math.pow(Math.max(0, Math.min(1, improvement)), 1.6);
}
