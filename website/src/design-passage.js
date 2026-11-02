import { createDesignExample } from './design-example.js';

// An illustrative sequence-level experiment leads into the one real chart.
// Scrolling changes presentation only, never benchmark values or chart state.
const passage = document.querySelector('.design-passage');
if (passage) {
  const scrollArea = passage.querySelector('.passage-scroll');
  const stage = passage.querySelector('.passage-stage');
  const exhibit = passage.querySelector('.passage-exhibit');
  const diagram = passage.querySelector('.passage-diagram');
  const results = passage.querySelector('.passage-results');
  const previous = passage.querySelector('.passage-previous');
  const next = passage.querySelector('.passage-next');
  const cue = passage.querySelector('.passage-cue');
  const skipLink = passage.querySelector('.passage-shortcut');
  // Viewport size changes spacing, never the one-scene scroll behaviour.
  const staticLayout = matchMedia('print');
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  // [Scroll distance in svh, illustration progress]. The reference is settled
  // throughout .125–.25; model proposals and completed plots also get reading holds.
  const timeline = [
    [0,0], [12,.025], [56,.105], [68,.125], [90,.25],
    [146,.33], [300,.53], [316,.53],
    // Read five independent single-edit sequences before measuring them.
    // Pause again on the first result before testing the remaining four.
    [376,.63], [396,.63], [442,.70], [458,.70], [582,.87],
  ];
  const [exampleDistance, exampleEnd] = timeline.at(-1);
  const pacing = { example:exampleDistance, comparison:60, handoff:90, results:100 };
  const handoffStart = pacing.example + pacing.comparison;
  const resultsReady = handoffStart + pacing.handoff;
  const scrollLength = resultsReady + pacing.results;
  let frame = 0, scrollFrame = 0, travel = 1, navHeight = 76, visible = true, focusResults = false, firstChart = true;
  let renderedProgress = NaN, renderedStatic = false;
  let resultsInert, diagramInert, cueOpacity, skipOpacity, frameHeight = 1, transportLength, transport, moving;
  const displayValues = new WeakMap();
  let activeStep = -1;
  const steps = [
    { start:0, name:'set the target', cue:'We start with an edit whose effect on RNA activity has been measured.', progress:.1875 },
    { start:90, name:'predict matching edits', cue:'We ask the model for other edits with a similar effect.', progress:.53 },
    { start:316, name:'test the edits', cue:'We test those edits to see how close they come to the target.', progress:.63 },
    { start:handoffStart + pacing.handoff * .40, name:'benchmark results', cue:'We repeat this across hundreds of targets to find out which models reach target responses with the fewest trials.', fade:6 },
  ];
  const clamp = n => Math.max(0, Math.min(1, n));
  const smooth = n => { const p = clamp(n); return p * p * (3 - 2 * p); };
  function progressAt(distance) {
    for (let i=1; i<timeline.length; i++) {
      const [from,a]=timeline[i-1], [to,b]=timeline[i];
      if (distance<=to) return a+(b-a)*clamp((distance-from)/(to-from));
    }
    return exampleEnd;
  }
  function distanceAt(progress) {
    const hold=timeline.findIndex(([,p],i)=>i>0 && p===progress && timeline[i-1][1]===progress);
    if (hold>0) return (timeline[hold-1][0]+timeline[hold][0])/2;
    for (let i=1; i<timeline.length; i++) {
      const [from,a]=timeline[i-1], [to,b]=timeline[i];
      if (progress<=b) return from+(to-from)*clamp((progress-a)/(b-a));
    }
    return exampleDistance;
  }
  const example = createDesignExample(diagram);
  function goToStep(index) {
    if (index === 3) { openResults(); return; }
    focusResults = false;
    if (location.hash === '#design-results') history.replaceState(null, '', '#design');
    if (staticLayout.matches) diagram.scrollIntoView({block:'start',behavior:'instant'});
    else goToProgress(distanceAt(steps[index].progress) / scrollLength, true);
  }
  previous.addEventListener('click', () => goToStep(Math.max(0,activeStep - 1)));
  next.addEventListener('click', () => goToStep(Math.min(3,activeStep + 1)));
  function show(element, opacity) {
    let previous = displayValues.get(element);
    if (!previous) displayValues.set(element, previous = {});
    const value = opacity.toFixed(4), visibility = opacity > .001 ? 'visible' : 'hidden';
    if (previous.opacity !== value) { element.style.opacity = value; previous.opacity = value; }
    if (previous.visibility !== visibility) { element.style.visibility = visibility; previous.visibility = visibility; }
  }
  function guide(distance) {
    const index = steps.findLastIndex(step => distance >= step.start);
    if (activeStep !== index) {
      activeStep = index;
      if (cue.textContent !== steps[index].cue) cue.textContent = steps[index].cue;
      previous.disabled = index === 0;
      previous.setAttribute('aria-label',index ? `Previous: ${steps[index - 1].name}` : 'Previous step');
      next.disabled = index === 3;
      next.setAttribute('aria-label',index === 3 ? 'Next step' : `Next: ${steps[index + 1].name}`);
      next.setAttribute('aria-controls',index === 2 ? 'design-results' : 'design-example');
    }
    // One text node fades through the transition; captions can never overlap.
    const entering = index ? smooth((distance - steps[index].start) / (steps[index].fade || 7)) : 1;
    const leaving = index < 3 ? smooth((steps[index + 1].start - distance) / (steps[index + 1].fade || 7)) : 1;
    const opacity = Math.min(entering,leaving).toFixed(3);
    if (cueOpacity !== opacity) { cue.style.opacity = opacity; cueOpacity = opacity; }
  }
  function syncAccess(isStatic, finished) {
    const returningFocus = !isStatic && !finished && results.contains(document.activeElement);
    if (returningFocus) (previous.disabled ? next : previous).focus({ preventScroll:true });
    const hideResults = !isStatic && !finished, hideDiagram = !isStatic && finished;
    if (resultsInert !== hideResults) {
      results.inert = resultsInert = hideResults;
      results.setAttribute('aria-hidden', String(hideResults));
    }
    if (!isStatic && finished && diagram.contains(document.activeElement)) {
      show(results, 1);
      results.focus({ preventScroll:true });
    }
    if (diagramInert !== hideDiagram) {
      diagram.inert = diagramInert = hideDiagram;
      diagram.setAttribute('aria-hidden', String(hideDiagram));
    }
  }
  function measure() {
    stopScroll();
    scrollArea.style.setProperty('--passage-travel', `${scrollLength}svh`);
    navHeight = parseFloat(getComputedStyle(stage).top) || 0;
    travel = Math.max(1, scrollArea.offsetHeight - stage.offsetHeight);
    frameHeight = exhibit.clientHeight;
    transport = transportLength = undefined;
    example.measure();
    renderedProgress = NaN;
    if (staticLayout.matches) {
      syncAccess(true, true);
      example.setProgress(1, true);
    }
    wake();
  }
  function draw() {
    frame = 0;
    if (!visible || document.hidden) return;
    const isStatic = staticLayout.matches;
    const p = isStatic ? 1 : clamp((navHeight - scrollArea.getBoundingClientRect().top) / travel);
    const distance = p * scrollLength;
    // Keep Skip clear through the results hold. Only fade after the pinned
    // chapter has released and its heading is passing beneath the masthead.
    const exitDistance = Math.max(0, navHeight - stage.getBoundingClientRect().top);
    const skipVisibility = isStatic ? 1 : 1 - smooth((exitDistance - 40) / 120);
    const skipValue = skipVisibility.toFixed(3);
    if (skipOpacity !== skipValue) {
      skipLink.style.opacity = skipValue;
      skipLink.inert = skipVisibility < .001;
      skipOpacity = skipValue;
    }
    const handoff = clamp((distance - handoffStart) / pacing.handoff);
    const exampleProgress = progressAt(distance);
    // Reuse unchanged frames during proposal/plot holds. Resize invalidates this cache.
    if (exampleProgress!==renderedProgress || isStatic!==renderedStatic) {
      example.setProgress(exampleProgress, isStatic);
      renderedProgress = exampleProgress;
      renderedStatic = isStatic;
    }
    // Both complete figures move as one vertical strip. Scroll changes their
    // position only; measurements never turn into aggregate benchmark values.
    const finished = isStatic || handoff>=.999;
    // Trim unused SVG letterboxing from the distance between the figures.
    // Both plots still clear the viewport edge before being hidden.
    if(transportLength===undefined) {
      const exampleBottom=diagram.querySelector('.response-axis-title').getBoundingClientRect().bottom-diagram.getBoundingClientRect().top;
      const chartTop=results.querySelector('.design-axis-label')?.getBoundingClientRect().top-results.getBoundingClientRect().top;
      transportLength=Math.max(exampleBottom+12,frameHeight-(chartTop||0)+12);
    }
    const isMoving=!isStatic&&handoff>0&&handoff<1;
    if(moving!==isMoving) { exhibit.classList.toggle('is-handoff',isMoving); moving=isMoving; }
    const offset = handoff * transportLength;
    const transportKey = isStatic ? 'print' : offset.toFixed(3);
    if(transportKey !== transport) {
      transport = transportKey;
      diagram.style.transform = isStatic ? 'none' : `translateY(${-offset}px)`;
      results.style.transform = isStatic ? 'none' : `translateY(${transportLength-offset}px)`;
    }
    guide(distance);
    syncAccess(isStatic, finished);
    show(diagram, isStatic || !finished ? 1 : 0);
    show(results, isStatic || handoff>0 ? 1 : 0);
    if (focusResults && finished) {
      focusResults = false;
      results.focus({ preventScroll:true });
    }
  }
  function wake() { if (!frame && visible && !document.hidden) frame = requestAnimationFrame(draw); }
  function stopScroll() { cancelAnimationFrame(scrollFrame); scrollFrame = 0; }
  function goToProgress(progress, animate = false) {
    measure();
    const from = scrollY;
    const to = scrollArea.getBoundingClientRect().top + from - navHeight + travel * progress;
    if (animate && !reducedMotion.matches) {
      // Browser smooth scrolling rushes several scenes into less than a second.
      // Only the step buttons use this timing; manual scrolling stays untouched.
      const duration = Math.min(3200, Math.max(900, Math.abs(to-from) / innerHeight * 1100));
      const start = performance.now();
      function advance(now) {
        const t = clamp((now-start) / duration);
        window.scrollTo({ top:from+(to-from)*smooth(t), behavior:'instant' });
        wake();
        scrollFrame = t < 1 ? requestAnimationFrame(advance) : 0;
      }
      scrollFrame = requestAnimationFrame(advance);
    } else window.scrollTo({ top:to, behavior:'instant' });
    wake();
  }
  function goToResults(skip = false) {
    measure();
    if (staticLayout.matches) results.scrollIntoView({ behavior:'instant', block:'start' });
    // The step arrow and direct links begin the reading hold; Skip lands
    // farther into it so continuing to scroll reaches the next section sooner.
    else goToProgress((resultsReady + (skip ? pacing.results * .6 : 1)) / scrollLength);
    wake();
  }
  skipLink.addEventListener('click', event => {
    if (event.defaultPrevented || event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    openResults(true);
  });
  function openResults(skip = false) {
    if (location.hash !== '#design-results') history.pushState(null, '', '#design-results');
    focusResults = true;
    goToResults(skip);
  }
  function followHash() { if (location.hash === '#design-results') goToResults(); }
  document.addEventListener('design:render', () => {
    const initial=firstChart;
    firstChart=false;
    requestAnimationFrame(() => { measure(); if(initial) followHash(); });
  });
  window.addEventListener('hashchange', () => { stopScroll(); followHash(); });
  window.addEventListener('popstate', stopScroll);
  window.addEventListener('pointerdown', stopScroll, { passive:true });
  window.addEventListener('wheel', stopScroll, { passive:true });
  window.addEventListener('touchstart', stopScroll, { passive:true });
  window.addEventListener('keydown', event => {
    if (['ArrowUp','ArrowDown','PageUp','PageDown','Home','End','Escape',' '].includes(event.key)) stopScroll();
  });
  window.addEventListener('scroll', wake, { passive:true });
  window.addEventListener('resize', measure, { passive:true });
  new ResizeObserver(measure).observe(scrollArea);
  new IntersectionObserver(entries => {
    visible = entries[0].isIntersecting;
    if (visible) measure();
    else { cancelAnimationFrame(frame); frame = 0; }
  }).observe(passage);
  staticLayout.addEventListener('change', measure);
  reducedMotion.addEventListener('change', measure);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { stopScroll(); cancelAnimationFrame(frame); frame = 0; }
    else wake();
  });
  window.addEventListener('pagehide', () => { stopScroll(); cancelAnimationFrame(frame); frame = 0; });
  window.addEventListener('pageshow', measure);
  document.fonts.ready.then(() => { measure(); followHash(); });
  measure();
}
