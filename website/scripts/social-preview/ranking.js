import { finite, ordered, overallScore } from "../../src/scoring.js";

// Include the complete fitted-readout subset, rather than picking winners.
// The score definition is shared with the live overview chart.
export function previewRanking(data) {
  return ordered(data.models.filter(model => model.kind === "foundation" && model.interface === "fitted"),
    model => overallScore(data, model.id), "lower").map(model => {
    const score = overallScore(data, model.id);
    if (!finite(score)) {
      throw new Error(`Review the social ranking for ${model.label}: score unavailable.`);
    }
    return { ...model, score };
  });
}

const IVORY = "#f0f0df";
const BAR_COLOUR = "#b8c6bb";

export function drawRanking(context, models) {
  function label(text, x, y, size = 18, colour = IVORY, align = "left", weight = 400) {
    context.font = `${weight} ${size}px Arial`;
    context.fillStyle = colour;
    context.textAlign = align;
    context.fillText(text, x, y);
  }
  function bar(x, y, width, height) {
    // One opaque, matte colour keeps every bar on the same visual footing.
    context.fillStyle = BAR_COLOUR;
    context.fillRect(x, y, width, height);
  }

  context.save();
  label("Higher is better ↑", 1120, 86, 16, "#bacabb", "right");
  const left = 80, width = 1040, bottom = 330, plotHeight = 224;
  const maximum = Math.ceil(Math.max(100, ...models.map(model => model.score)) / 50) * 50;
  const minimum = Math.floor(Math.min(0, ...models.map(model => model.score)) / 50) * 50;
  const scale = plotHeight / (maximum - minimum);
  const position = score => bottom - (score - minimum) * scale;
  // Align the outside bar edges with the title, rather than leaving half a
  // category slot empty at either side of the composition.
  const barWidth = Math.min(57, width / models.length * .52);
  const step = models.length > 1 ? (width - barWidth) / (models.length - 1) : 0;
  models.forEach((model, i) => {
    const centre = models.length > 1 ? left + barWidth / 2 + i * step : left + width / 2;
    const top = position(Math.max(0, model.score));
    bar(centre - barWidth / 2, top, barWidth, Math.abs(model.score) * scale);
    // Keep small-preview numerals crisp across both light and dark folds.
    // The shadow follows the glyphs without dimming the surrounding field.
    context.save();
    context.shadowColor = "rgba(7, 31, 28, .75)";
    context.shadowBlur = 3;
    context.shadowOffsetY = 1;
    label(model.score.toFixed(1), centre, top - 12, 25, "#f5f4e9", "center", 600);
    context.restore();
    const nt = model.label.match(/^(NTv3) (\S+ (?:pre|post))$/);
    const names = nt ? [nt[1], nt[2]] : model.label === "GENERATORv2" ? ["GENERATOR", "v2"] : [model.label];
    names.forEach((line, j) => label(line, centre, bottom + 26 + j * 21, j ? 16 : 18, j ? "#b7c9b8" : IVORY, "center"));
  });

  context.restore();
}
