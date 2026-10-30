import { initOverviewScoreInteractions, renderOverviewScoreChart } from "./overview-score-chart.js";

// These explain the biological questions. Exact metrics remain in task details.
const categories = [
  {
    id:"priors", label:"Sequence priors", color:"#9C7524",
    text:"Predict a missing base from surrounding DNA.",
    equation:'<i>p</i>(base | surrounding DNA)',
    equationLabel:"Probability of a base given the surrounding DNA.",
  },
  {
    id:"prediction", label:"Functional prediction", color:"#2463A6",
    text:"Predict an edit’s effect on RNA splicing.",
    equation:'Δ = <i>f</i>(edited) − <i>f</i>(original)',
    equationLabel:"The edit effect is the predicted response to edited DNA minus the predicted response to original DNA.",
  },
  {
    id:"context", label:"Biological context", color:"#19836E",
    text:"Predict expression and edit effects across cells and tissues.",
    equation:'Δ<sub>HepG2</sub> − Δ<sub>K562</sub>',
    equationLabel:"The effect of the same edit in HepG2 cells minus its effect in K562 cells.",
  },
  {
    id:"interactions", label:"Genetic interactions", color:"#7956A5",
    text:"Predict how surrounding DNA changes an edit’s effect.",
    equation:'Δ<sub>background A</sub> − Δ<sub>background B</sub>',
    equationLabel:"The effect of the same edit in background A minus its effect in background B.",
  },
  {
    id:"design", label:"Genomic design", color:"#BE4D35",
    text:"Find edits or sequences with a chosen effect.",
    equation:'<span class="overview-equation-prefix">Matching:</span> min |Δ − Δ<sub>ref</sub>|',
    equationLabel:"For response matching, minimise the absolute difference between a candidate’s predicted edit effect and the reference edit’s predicted effect.",
  },
];

// Small conceptual drawings share a sequence-and-response vocabulary.
// They carry no benchmark values; the explanatory text provides their meaning.
// Every schematic response uses the same stroke and filled endpoint.
function responseLine(start, end, y, muted = false) {
  return `<g class="category-readout${muted ? " is-muted" : ""}">
    <path class="category-readout-line" d="M${start} ${y}H${end}"/>
    <circle class="category-readout-end" cx="${end}" cy="${y}" r="2.5"/>
  </g>`;
}

function categoryDiagram(id) {
  const bases = (sequence, y, active, x = 24, step = 25) => [...sequence].map((base, i) => `<text x="${x + i * step}" y="${y}" class="${i === active ? "category-ink" : "category-base"}">${base}</text>`).join("");
  const diagrams = {
    priors: `<path class="category-guide" d="M13 41H187"/>
      ${bases("AC?GTA", 34, 2, 24, 29)}
      <path class="category-ink" d="M70 17V12H94V17M70 44V49H94V44"/>
      <path class="category-ink category-signal" d="M73 61V57M82 61V52M91 61V58"/>`,
    prediction: `<text x="27" y="35" class="category-base">C</text><text x="76" y="35" class="category-ink">T</text>
      <path class="category-guide" d="M42 28H60M55 23L60 28L55 33"/>
      ${responseLine(106,145,21,true)}${responseLine(106,179,44)}`,
    context: `<text x="22" y="37" class="category-base">C</text><text x="50" y="37" class="category-ink">T</text>
      <path class="category-guide" d="M30 31H39M36 28L39 31L36 34M65 31H82M82 31V15H99M82 31V49H99"/>
      <circle class="category-outline" cx="114" cy="15" r="11"/><circle class="category-outline" cx="114" cy="49" r="11"/>
      <circle class="category-dot" cx="115" cy="14" r="3"/><circle class="category-dot" cx="112" cy="50" r="3"/>
      ${responseLine(135,182,15)}${responseLine(135,155,49)}`,
    interactions: `${[24,54].map((y, row) => `<text x="14" y="${y}" class="category-base">${row ? "G" : "A"}</text>
      <text x="38" y="${y}" class="category-ink">C</text><text x="78" y="${y}" class="category-ink">T</text>
      <text x="102" y="${y}" class="category-base">${row ? "A" : "G"}</text>
      <path class="category-ink" d="M51 ${y - 6}H64M60 ${y - 10}L64 ${y - 6}L60 ${y - 2}"/>
      ${responseLine(128,row ? 151 : 184,y-6)}`).join("")}`,
    design: `<path class="category-guide" stroke-dasharray="2 3" d="M170 6V62"/>
      ${[14,30,46].map((y, row) => `<path class="${row === 1 ? "category-ink" : "category-guide"}" d="M18 ${y}H88"/>${[26,38,50,62,74,86].map((x, i) => `<path class="${i === row + 1 ? "category-ink" : "category-guide"}" d="M${x} ${y - 4}V${y + 4}"/>`).join("")}${responseLine(115,[143,170,151][row],y,row !== 1)}`).join("")}
      <path class="category-ink" d="M12 24H8V36H12"/>`,
  };
  return `<svg class="overview-category-drawing" viewBox="0 0 200 68" aria-hidden="true" focusable="false">${diagrams[id]}</svg>`;
}

export function initOverview(data) {
  const root = document.querySelector("#overview");
  root.innerHTML = `<div class="overview-introduction">
    <h2 class="overview-lead">How close are we to reliable DNA design?</h2>
    <p class="overview-copy">We built BEND 2.0 to test whether genomic models can guide the design of DNA. Across eight tasks, we examine how they predict sequence function, account for cell type and genetic background, and choose sequences that produce a desired response.</p>
  </div>
  <div id="overview-scores">${renderOverviewScoreChart(data)}</div>`;
  initOverviewScoreInteractions(root.querySelector("#overview-scores"));

  document.querySelector("#category-guide").innerHTML = `<div class="overview-categories">
    ${categories.map(category => `<figure class="overview-category" style="--category:${category.color}">
      ${categoryDiagram(category.id)}
      <figcaption>
        <h3 class="overview-category-name">${category.label}</h3>
        <p class="overview-category-description">${category.text}</p>
        <p class="overview-category-equation" role="math" aria-label="${category.equationLabel}"><span aria-hidden="true">${category.equation}</span></p>
      </figcaption>
    </figure>`).join("")}
  </div>`;
}
