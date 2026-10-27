const fmt = (x, d = 1) => x.toFixed(d);
export function budgetExplorer(data, budget = 10) {
  const ids = ["alphagenome", "ntv3_650m_post", "uniform"];
  const colors = ["#be4d35", "#385e78", "#8b8983"];
  const labels = [
    "AlphaGenome · native",
    "NTv3 650M post · fitted",
    "Uniform selection",
  ];
  const series = ids.map((id) =>
    data.supplementary.repairBudgets.series.find((s) => s.modelId === id),
  );
  const W = 720,
    H = 264,
    L = 42,
    R = 24,
    T = 17,
    B = 38,
    x = (k) => L + ((k - 1) / 24) * (W - L - R),
    y = (v) => H - B - v * (H - T - B);
  const guides = [0, 0.25, 0.5, 0.75, 1]
    .map(
      (v) =>
        `<g><line x1="${L}" y1="${y(v)}" x2="${W - R}" y2="${y(v)}" stroke="#d5cfc3" stroke-width="1"/><text x="${L - 10}" y="${y(v) + 4}" text-anchor="end" fill="#68675f" font-size="10">${v * 100}%</text></g>`,
    )
    .join("");
  const ticks = [1, 5, 10, 25]
    .map(
      (k) =>
        `<text x="${x(k)}" y="${H - B + 21}" text-anchor="middle" fill="#68675f" font-size="11">${k}</text>`,
    )
    .join("");
  const lines = series
    .map((s, i) => {
      const points = s.points
        .map((p) => `${x(p.budget)},${y(p.successRate)}`)
        .join(" ");
      const area = s.points
        .map((p) => `${x(p.budget)},${y(p.ciHigh)}`)
        .concat(
          [...s.points].reverse().map((p) => `${x(p.budget)},${y(p.ciLow)}`),
        )
        .join(" ");
      return `<polygon points="${area}" fill="${colors[i]}" opacity=".06"/><polyline points="${points}" fill="none" stroke="${colors[i]}" stroke-width="2" ${i === 2 ? 'stroke-dasharray="5 4"' : ""}/>${s.points.map((p) => `<circle cx="${x(p.budget)}" cy="${y(p.successRate)}" r="${p.budget === budget ? 4.5 : 2.7}" fill="${p.budget === budget ? colors[i] : "#f4f1e9"}" stroke="${colors[i]}" stroke-width="1.5"><title>${labels[i]}, ${p.budget} choices: ${fmt(p.successRate * 100)}%</title></circle>`).join("")}`;
    })
    .join("");
  return `<p>A target is reached when at least one tested edit matches the reference response within assay uncertainty.</p><div class="budget-controls"><span>Edits tested</span><div role="group" aria-label="Number of candidates to test">${[1, 5, 10, 25].map((k) => `<button data-budget="${k}" aria-pressed="${budget === k}">${k} ${k === 1 ? "edit" : "edits"}</button>`).join("")}</div></div><div class="budget-chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Fraction of response targets reached versus candidates tested, for AlphaGenome native, NTv3 650M post fitted, and uniform selection. Exact values appear below." style="font-family:Arial,Helvetica,sans-serif;width:100%;height:auto">${guides}${ticks}<line x1="${x(budget)}" x2="${x(budget)}" y1="${T}" y2="${H - B}" stroke="#aaa295" stroke-dasharray="3 3"/>${lines}<text x="${W / 2}" y="${H - 2}" text-anchor="middle" fill="#68675f" font-size="10">Candidates tested</text></svg></div><div class="budget-readout" aria-live="polite">${series
    .map((s, i) => {
      const p = s.points.find((p) => p.budget === budget);
      return `<div style="--category:${colors[i]}"><small><i class="category-dot"></i>${labels[i]}</small><strong>${fmt(p.successRate * 100)}<span>%</span></strong><em>95% interval ${fmt(p.ciLow * 100)}–${fmt(p.ciHigh * 100)}%</em></div>`;
    })
    .join(
      "",
    )}</div><details class="dialog-details"><summary>Evaluation details</summary><div><p>Shaded bands show reported 95% intervals. Lines connect the four evaluated budgets; intermediate budgets were not evaluated.</p><p>These success rates accompany Figure 5B. Table 1 reports the first edit’s residual rank.</p></div></details>`;
}
