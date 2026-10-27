import * as THREE from "three";
import { fluxVertex, fluxFragment } from "../../src/hero-flux.js";
import { previewRanking, drawRanking } from "./ranking.js";

// A deterministic, card-specific composition of the hero's Grainient field.
// Retains its palette, domain warp and grain; see src/react-bits-LICENSE.md.
// This authoring page is local-only; crawlers receive the exported PNG.
const WIDTH = 1200, HEIGHT = 630, FIELD_HEIGHT = 480;
const canvas = document.querySelector("#output");
const context = canvas.getContext("2d");
const frame = document.querySelector("#frame");
const status = document.querySelector("#status");
const download = document.querySelector("#download");
const parameters = new URLSearchParams(location.search);
frame.value = ["0", "12", "24", "36", "42", "48", "60", "72", "84"].includes(parameters.get("frame")) ? parameters.get("frame") : "48";

try {
  const response = await fetch("../../data/benchmark.json");
  if (!response.ok) throw new Error("Could not load benchmark scores.");
  const data = await response.json();
  const models = previewRanking(data);
  // Reuse the favicon's vector artwork as the card identity. Tint its alpha
  // mask in memory so the card is deterministic in either system colour mode.
  const favicon = new Image();
  favicon.src = new URL("../../assets/mark.svg", import.meta.url).href;
  await favicon.decode();
  const mark = document.createElement("canvas");
  mark.width = mark.height = 256;
  const markContext = mark.getContext("2d");
  markContext.drawImage(favicon, 0, 0, mark.width, mark.height);
  markContext.globalCompositeOperation = "source-in";
  markContext.fillStyle = "#f5f4e9";
  markContext.fillRect(0, 0, mark.width, mark.height);
  // More interleaving folds and stronger relief give the still depth. Keep the
  // live shader untouched, and fail visibly if its source changes underneath.
  const previewFragment = [
    ["const float BANDS = 2.15;", "const float BANDS = 3.05;"],
    ["const float FLOW = 2.15;", "const float FLOW = 2.4;"],
    ["const float SILK = .40;", "const float SILK = .52;"],
    ["grain * .048", "grain * .038"],
  ].reduce((source, [original, replacement]) => {
    if (source.split(original).length !== 2) {
      throw new Error("The hero shader changed; review the social preview's lighting adjustments.");
    }
    return source.replace(original, replacement);
  }, fluxFragment);

  await document.fonts.load('400 76px "Newsreader"');
  const renderer = new THREE.WebGLRenderer({ antialias:false, alpha:false, preserveDrawingBuffer:true });
  renderer.setPixelRatio(1);
  renderer.setSize(WIDTH, HEIGHT, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const uniforms = {
    uTime:{value:0}, uViewScale:{value:HEIGHT / FIELD_HEIGHT}, uNarrow:{value:1},
    uAspect:{value:WIDTH / FIELD_HEIGHT}, uPresence:{value:0}, uDpr:{value:1},
    uPointer:{value:new THREE.Vector2(2.5, .6)},
  };
  const geometry = new THREE.PlaneGeometry(2, 2);
  const material = new THREE.ShaderMaterial({
    uniforms, vertexShader:fluxVertex, fragmentShader:previewFragment,
    depthTest:false, depthWrite:false, toneMapped:false,
  });
  const scene = new THREE.Scene();
  scene.add(new THREE.Mesh(geometry, material));
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

  function render() {
    uniforms.uTime.value = Number(frame.value);
    renderer.render(scene, camera);
    context.clearRect(0, 0, WIDTH, HEIGHT);
    // Reorient the hero's vertical shading: luminous folds around the ranking,
    // with a naturally quiet lower ground for the title. No added dark overlay.
    context.save();
    context.translate(0, HEIGHT);
    context.scale(1, -1);
    context.drawImage(renderer.domElement, 0, 0);
    context.restore();

    context.textBaseline = "alphabetic";
    // Compensate for the SVG's own inset so the visible mark aligns at x80.
    context.save();
    context.fillStyle = "#f5f4e9";
    context.shadowColor = "rgba(7, 31, 28, .5)";
    context.shadowBlur = 3;
    context.shadowOffsetY = 1;
    context.drawImage(mark, 70, 40, 116, 116);
    context.font = '400 40px "Newsreader"';
    context.fillText("2.0", 193, 148);
    context.restore();
    context.fillStyle = "#f0f0df";
    context.font = '400 76px "Newsreader"';
    ["Benchmarking the Capabilities", "Needed to Design DNA"]
      .forEach((line, i) => context.fillText(line, 80, 472 + i * 86));
    drawRanking(context, models);

    const png = canvas.toDataURL("image/png");
    download.href = png;
    download.removeAttribute("aria-disabled");
    document.querySelector("#half").src = png;
    document.querySelector("#small").src = png;
    status.textContent = `${WIDTH} × ${HEIGHT} PNG · ${models.length} fitted-readout configurations · shader time ${frame.value}s`;
    history.replaceState(null, "", `?frame=${frame.value}`);
  }
  frame.addEventListener("change", render);
  render();
  window.addEventListener("pagehide", () => { geometry.dispose(); material.dispose(); renderer.dispose(); }, { once:true });
} catch (error) {
  status.textContent = `Could not render the preview: ${error.message}`;
}
