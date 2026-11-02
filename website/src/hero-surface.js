import * as THREE from "three";
import { fluxVertex, fluxFragment } from "./hero-flux.js";

// Grainient colour fields flow through a textured, softly lit material.
const ART = { maxPixels: 1600000, fps: 60, forest: "#081a19" };
const SCENE_PREROLL = 120;
const canvas = document.querySelector("#hero-surface");
const hero = document.querySelector(".publication-header");
const atmosphere = document.querySelector(".hero-atmosphere");

function initializeSurface() {
  if (!canvas || !hero || !atmosphere) return;
  const cleanupKey = Symbol.for("bend.field.cleanup");
  canvas[cleanupKey]?.();
  const preference = matchMedia("(prefers-reduced-motion: reduce)");
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({
      canvas, alpha: true, antialias: false, depth: false, stencil: false,
      powerPreference: "low-power",
    });
  } catch { canvas.hidden = true; return; }
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.setClearColor(ART.forest, 0);
  const uniforms = {
    uTime: { value: 0 }, uViewScale: { value: 1 }, uNarrow: { value: 0 },
    uAspect: { value: 3.5 }, uPresence: { value: 0 },
    uDpr: { value: 1 },
    uPointer: { value: new THREE.Vector2(2.5, .6) },
  };
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  const geometry = new THREE.PlaneGeometry(2, 2);
  const material = new THREE.ShaderMaterial({
    uniforms, vertexShader: fluxVertex, fragmentShader: fluxFragment,
    transparent: true, premultipliedAlpha: true, depthTest: false, depthWrite: false, toneMapped: false,
  });
  const surface = new THREE.Mesh(geometry, material);
  surface.frustumCulled = false;
  scene.add(surface);

  let width = 1, height = 1, heroHeight = 430, aspect = 3.5, narrow = 0;
  let visible = true, lost = false, disposed = false, ready = false;
  let regionsDirty = true, regions = [];
  // Ambient motion is explicitly requested. Reduced motion removes cursor lag.
  let frame = 0, previous = 0, nextDraw = 0, time = 0;
  let px = 2.5, py = .6, sx = px, sy = py, presence = 0, active = 0;
  let pointerId = null, pointerSurface = null, captureSurface = null;
  const listeners = [];
  const on = (target, event, action, options) => {
    target.addEventListener(event, action, options);
    listeners.push(() => target.removeEventListener(event, action, options));
  };
  const windows = [...document.querySelectorAll("[data-scene-window]")];
  const seen = new Map(windows.map(element => {
    const bounds = element.getBoundingClientRect();
    return [element, bounds.width > 0 && bounds.height > 0 && bounds.bottom > -SCENE_PREROLL && bounds.top < innerHeight + SCENE_PREROLL];
  }));
  visible = [...seen.values()].some(Boolean);
  function measureRegions() {
    // Keep the full viewport's coordinates, but shade only exposed openings.
    // Two render pixels protect fractional edges even below 1x resolution.
    // The overlap remains behind opaque content.
    const padding = 2 / renderer.getPixelRatio();
    const openings = windows.map(element => {
      const bounds = element.getBoundingClientRect();
      // Native rubber-banding can move paper without exposing that displacement
      // to layout APIs. Paint ahead near the top, including behind the paper,
      // so any part of the viewport it reveals already contains moving light.
      if (element === hero && window.scrollY <= 120) return [0, height];
      if (element === hero) return [0, Math.min(height, bounds.bottom + padding)];
      // The closing text scrolls over a fixed canvas. A scissor edge following
      // that text can trail compositor scrolling by a frame, leaving a band
      // behind the content. Keep this backing complete while the closing
      // section is nearby; opaque sections still cover the extra pixels.
      return bounds.bottom > -SCENE_PREROLL && bounds.top < height + SCENE_PREROLL
        ? [0, height] : [0, 0];
    }).filter(([top, bottom]) => bottom > top).sort((a, b) => a[0] - b[0]);
    regions = [];
    for (const [top, bottom] of openings) {
      const last = regions.at(-1);
      if (last && top <= last[1]) last[1] = Math.max(last[1], bottom);
      else regions.push([top, bottom]);
    }
    regionsDirty = false;
  }
  function stop() {
    if (frame) cancelAnimationFrame(frame);
    frame = 0; previous = 0; nextDraw = 0;
  }
  function draw(now) {
    frame = 0;
    if (disposed || lost || !ready || !visible || document.hidden) return;
    const interval = 1000 / ART.fps;
    if (nextDraw && now + .8 < nextDraw) {
      frame = requestAnimationFrame(draw); return;
    }
    // Carry the fractional frame budget across refresh rates such as 90/144 Hz.
    nextDraw = !nextDraw || now - nextDraw > interval ? now + interval : nextDraw + interval;
    const dt = previous ? Math.min((now - previous) / 1000, .05) : 0;
    previous = now;
    time += dt;
    const ease = preference.matches ? 1 : 1 - Math.exp(-dt * 24);
    sx += (px - sx) * ease; sy += (py - sy) * ease;
    presence += (active - presence) * (1 - Math.exp(-dt * (active ? 14 : 8)));
    uniforms.uViewScale.value = height / heroHeight;
    uniforms.uAspect.value = aspect;
    uniforms.uNarrow.value = narrow;
    uniforms.uTime.value = time; uniforms.uPointer.value.set(sx, sy);
    uniforms.uPresence.value = presence;
    if (regionsDirty) measureRegions();
    renderer.setScissorTest(true);
    for (const [top, bottom] of regions) {
      renderer.setScissor(0, height - bottom, width, bottom - top);
      renderer.render(scene, camera);
    }
    if (disposed || lost) return;
    canvas.hidden = false;
    frame = requestAnimationFrame(draw);
  }
  function wake() {
    if (!frame && ready && !disposed && !lost && visible && !document.hidden) {
      previous = 0; nextDraw = 0; frame = requestAnimationFrame(draw);
    }
  }
  function release() {
    const changed = active || presence > .0001 || pointerId !== null;
    const captured = pointerId, owner = captureSurface;
    active = 0; pointerId = null; captureSurface = null;
    if (captured !== null && owner?.hasPointerCapture?.(captured)) owner.releasePointerCapture(captured);
    if (changed) wake();
  }
  function resize() {
    const bounds = atmosphere.getBoundingClientRect();
    if (!bounds.width || !bounds.height || disposed || lost) return;
    width = bounds.width; height = bounds.height;
    heroHeight = hero.getBoundingClientRect().height || 430;
    aspect = width / heroHeight;
    narrow = 1 - THREE.MathUtils.smoothstep(width, 600, 1050);
    release(); presence = 0;
    const pixelRatio = Math.min(devicePixelRatio || 1, 1.75, Math.sqrt(ART.maxPixels / (width * height)));
    uniforms.uDpr.value = pixelRatio;
    renderer.setPixelRatio(pixelRatio);
    renderer.setSize(width, height, false);
    regionsDirty = true;
    wake();
  }
  function point(event, element) {
    // Hovering text or links keeps the same light. Touch capture is excluded
    // separately on controls so their normal taps and clicks remain untouched.
    // Every opening reveals the same hero-scaled material and cursor light.
    px = THREE.MathUtils.clamp(event.clientX / heroHeight, -.25, aspect + .25);
    const bottom = element === hero ? 1.5 : height / heroHeight + .25;
    py = THREE.MathUtils.clamp(event.clientY / heroHeight, -.25, bottom);
    if (!active || pointerSurface !== element) {
      sx = px; sy = py;
      // Fresh entry fades in at the hand, including during a previous fade-out;
      // a partly visible light must not jump across the hero on rapid re-entry.
      presence = 0;
    }
    pointerSurface = element; active = 1;
  }
  windows.forEach(element => {
    on(element, "pointerenter", event => {
      if (event.pointerType !== "touch") { point(event, element); wake(); }
    });
    on(element, "pointermove", event => {
      if (pointerId !== null && event.pointerId !== pointerId) return;
      if (event.pointerType === "touch" && pointerId === null) return;
      point(event, element); wake();
    }, { passive: true });
    on(element, "pointerdown", event => {
      if (event.pointerType !== "touch" || pointerId !== null || event.target?.closest("a, button")) return;
      point(event, element); pointerId = event.pointerId; captureSurface = element;
      element.setPointerCapture?.(pointerId); wake();
    });
    on(element, "pointerup", event => { if (event.pointerId === pointerId) release(); });
    on(element, "pointercancel", event => {
      if (pointerId === null || event.pointerId === pointerId) release();
    });
    on(element, "lostpointercapture", () => { if (captureSurface === element) release(); });
    on(element, "pointerleave", () => { if (pointerId === null && pointerSurface === element) release(); });
  });
  on(window, "blur", release);
  on(window, "scroll", () => { regionsDirty = true; release(); }, { passive: true });
  on(preference, "change", () => { release(); stop(); wake(); });
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(atmosphere); resizeObserver.observe(hero);
  // Fonts, expanding rows and chart layout can move an opening without scrolling.
  const regionObserver = new ResizeObserver(() => { regionsDirty = true; wake(); });
  windows.forEach(element => regionObserver.observe(element));
  const main = document.querySelector(".atlas-main");
  if (main) regionObserver.observe(main);
  const intersectionObserver = new IntersectionObserver(entries => {
    regionsDirty = true;
    entries.forEach(entry => seen.set(entry.target, entry.isIntersecting));
    if (pointerSurface && !seen.get(pointerSurface)) { release(); presence = 0; }
    visible = [...seen.values()].some(Boolean);
    if (visible) wake(); else stop();
  }, { rootMargin: `${SCENE_PREROLL}px 0px` });
  windows.forEach(element => intersectionObserver.observe(element));
  on(document, "visibilitychange", () => {
    if (document.hidden) { release(); stop(); } else wake();
  });
  on(window, "pagehide", stop); on(window, "pageshow", wake);
  on(canvas, "webglcontextlost", event => {
    event.preventDefault(); lost = true; release(); stop(); canvas.hidden = true;
  });
  on(canvas, "webglcontextrestored", () => { lost = false; resize(); });
  canvas[cleanupKey] = () => {
    disposed = true; release(); stop(); canvas.hidden = true;
    resizeObserver.disconnect(); regionObserver.disconnect(); intersectionObserver.disconnect();
    listeners.forEach(remove => remove());
    geometry.dispose(); material.dispose(); renderer.dispose();
    delete canvas[cleanupKey];
  };
  renderer.debug.onShaderError = () => {
    disposed = true; stop(); canvas.hidden = true;
    queueMicrotask(() => canvas[cleanupKey]?.());
    console.warn("The header uses its static background.");
  };
  canvas.hidden = true;
  resize(); ready = true; wake();
}
if ("requestIdleCallback" in window)
  window.requestIdleCallback(initializeSurface, { timeout: 500 });
else setTimeout(initializeSurface, 32);
