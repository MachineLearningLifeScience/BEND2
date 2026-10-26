export function initPageNavigation({ updateTableOverflow = () => {} } = {}) {
  const header = document.querySelector(".research-header");
  const nav = header?.querySelector(".page-nav");
  if (!nav) return () => {};

  const panel = header.querySelector(".navigation-panel");
  const brand = header.querySelector(".research-brand");
  const toggle = header.querySelector(".navigation-toggle");
  const current = header.querySelector(".navigation-current");
  const publications = header.querySelector(".publication-links");
  const hero = document.querySelector(".publication-header");
  const topLinks = [...document.querySelectorAll('a[href="#top"]')];
  const entries = [...nav.querySelectorAll('a[href^="#"]')]
    .map(link => ({ link, hash: link.getAttribute("href"), section: document.querySelector(link.getAttribute("href")) }))
    .filter(entry => entry.section);
  const compact = window.matchMedia("(max-width: 800px)");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const removers = [];
  let mobile = compact.matches;
  let navigationOpen = false;
  let active = -1;
  let frame = 0;
  let topFrame = 0, restoreScrollBehavior = null;
  let renderedBlend = -1, renderedCover = -1, measuredHeight = -1;
  let renderedOverscroll = null;

  function listen(target, type, handler, options) {
    if (!target) return;
    target.addEventListener(type, handler, options);
    removers.push(() => target.removeEventListener(type, handler, options));
  }
  function renderMenus() {
    if (panel) panel.hidden = mobile && !navigationOpen;
    if (toggle) {
      toggle.hidden = !mobile;
      toggle.setAttribute("aria-expanded", String(mobile && navigationOpen));
      toggle.setAttribute("aria-label", navigationOpen ? "Close navigation" : "Open navigation");
    }
  }
  function closeNavigation(restoreFocus = false) {
    if (!navigationOpen) return;
    navigationOpen = false;
    renderMenus();
    if (restoreFocus) toggle?.focus({ preventScroll: true });
  }
  function setActive(index) {
    if (index === active) return;
    active = index;
    entries.forEach(({ link }, i) => {
      if (i === active) link.setAttribute("aria-current", "location");
      else link.removeAttribute("aria-current");
    });
    if (current && entries[active]) current.textContent = entries[active].link.textContent.trim().replace(/\s+/g, " ");
  }
  function update() {
    frame = 0;
    const height = header.getBoundingClientRect().height;
    const heroBounds = hero?.getBoundingClientRect();
    // Enable the native top bounce before an upward gesture reaches the edge.
    // Below the hero, keep the page's bottom boundary firm.
    const overscroll = heroBounds && heroBounds.bottom > height ? "auto" : "none";
    const offset = height + 100;
    let index = 0;
    // Finish geometry reads before changing the masthead or hero styles.
    // Closed menus still track the page: their links have no layout rectangles.
    entries.forEach(({ section }, i) => {
      if (section.getBoundingClientRect().top <= offset) index = i;
    });
    if (entries.length && window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 4)
      index = entries.length - 1;
    // Follow the last stretch of the hero, reaching opaque paper before content
    // passes under the masthead. No timed transition trails the user's scroll.
    const distance = heroBounds ? Math.min(100, heroBounds.height * .25) : 100;
    const progress = Math.max(0, Math.min(1, heroBounds
      ? 1 - (heroBounds.bottom - height) / distance
      : window.scrollY / distance));
    const blend = progress * progress * (3 - 2 * progress);
    // Switch contrast polarity rather than passing pale text through grey.
    const reading = blend >= .43;
    const inkBlend = reading ? (blend - .43) / .57 : blend / .43;
    if (overscroll !== renderedOverscroll) {
      document.documentElement.style.setProperty("--page-overscroll", overscroll);
      renderedOverscroll = overscroll;
    }
    if (blend !== renderedBlend) {
      header.style.setProperty("--nav-paper", blend.toFixed(4));
      header.style.setProperty("--nav-paper-percent", `${(blend * 100).toFixed(2)}%`);
      header.style.setProperty("--nav-ink-blend", `${(inkBlend * 100).toFixed(2)}%`);
      header.classList.toggle("is-reading", reading);
      renderedBlend = blend;
    }
    if (heroBounds) {
      const cover = Math.min(heroBounds.height, Math.max(0, height - heroBounds.top));
      if (cover !== renderedCover) {
        hero.style.setProperty("--nav-cover", `${cover}px`);
        renderedCover = cover;
      }
    }
    setActive(index);
  }
  function scheduleUpdate() {
    if (!frame) frame = window.requestAnimationFrame(update);
  }
  function measureHeader() {
    const height = header.getBoundingClientRect().height;
    if (height !== measuredHeight) {
      document.documentElement.style.setProperty("--section-nav-height", `${height}px`);
      measuredHeight = height;
    }
    updateTableOverflow();
    scheduleUpdate();
  }
  function syncLayout() {
    stopTopScroll();
    if (mobile !== compact.matches) {
      const focused = document.activeElement;
      mobile = compact.matches;
      navigationOpen = false;
      renderMenus();
      // Do not strand focus in a panel or control hidden by the new layout.
      if (mobile && panel?.contains(focused))
        toggle?.focus({ preventScroll: true });
      else if (!mobile && focused === toggle)
        entries[active]?.link.focus({ preventScroll: true });
    }
    measureHeader();
  }
  function nativeLinkClick(event, link) {
    return event.defaultPrevented || event.button > 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey ||
      link.hasAttribute("download") || (link.getAttribute("target") && link.getAttribute("target") !== "_self");
  }

  entries.forEach(({ link, hash, section }, index) => listen(link, "click", event => {
    if (nativeLinkClick(event, link)) return;
    event.preventDefault();
    stopTopScroll();
    closeNavigation();
    if (window.location.hash !== hash) {
      const url = new URL(window.location.href);
      url.hash = hash;
      window.history.pushState(null, "", url);
    }
    // A selected link can now be hidden; keep keyboard reading at its destination.
    if (!section.hasAttribute("tabindex")) section.setAttribute("tabindex", "-1");
    section.focus({ preventScroll: true });
    section.scrollIntoView({ behavior: reducedMotion.matches ? "auto" : "smooth", block: "start" });
    setActive(index);
  }));
  function stopTopScroll() {
    if (topFrame) window.cancelAnimationFrame(topFrame);
    topFrame = 0;
    if (restoreScrollBehavior !== null) {
      document.documentElement.style.scrollBehavior = restoreScrollBehavior;
      restoreScrollBehavior = null;
    }
  }
  function scrollToTop() {
    stopTopScroll();
    const from = window.scrollY;
    if (from < 1) return;
    // The top link uses a short scroll animation even with reduced motion.
    const duration = Math.min(460, 260 + from * .05);
    restoreScrollBehavior = document.documentElement.style.scrollBehavior;
    document.documentElement.style.scrollBehavior = "auto";
    let started;
    const step = time => {
      started ??= time;
      const progress = Math.min(1, (time - started) / duration);
      const eased = progress < .5 ? 4 * progress ** 3 : 1 - (-2 * progress + 2) ** 3 / 2;
      window.scrollTo({ top: from * (1 - eased), behavior: "auto" });
      if (progress < 1) topFrame = window.requestAnimationFrame(step);
      else stopTopScroll();
    };
    topFrame = window.requestAnimationFrame(step);
  }
  topLinks.forEach(link => listen(link, "click", event => {
    if (nativeLinkClick(event, link)) return;
    event.preventDefault();
    closeNavigation();
    if (window.location.hash !== "#top") {
      const url = new URL(window.location.href);
      url.hash = "top";
      window.history.pushState(null, "", url);
    }
    brand?.focus({ preventScroll: true });
    scrollToTop();
  }));
  listen(window, "wheel", stopTopScroll, { passive: true });
  listen(window, "touchstart", stopTopScroll, { passive: true });
  listen(window, "pointerdown", stopTopScroll, { passive: true });
  listen(window, "keydown", event => {
    if (["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", " ", "Escape"].includes(event.key)) stopTopScroll();
  });
  listen(toggle, "click", () => {
    navigationOpen = !navigationOpen;
    renderMenus();
  });
  listen(publications, "click", event => {
    const link = event.target.closest("a");
    if (!link || event.defaultPrevented || event.button > 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (mobile) closeNavigation(true);
  });
  listen(document, "pointerdown", event => {
    if (mobile && navigationOpen && !header.contains(event.target)) closeNavigation();
  });
  listen(document, "focusin", event => {
    if (mobile && navigationOpen && !header.contains(event.target)) closeNavigation();
  });
  listen(document, "keydown", event => {
    if (event.key !== "Escape" || event.defaultPrevented) return;
    if (mobile && navigationOpen) {
      event.preventDefault();
      closeNavigation(true);
    }
  });
  listen(window, "scroll", scheduleUpdate, { passive: true });
  listen(window, "resize", syncLayout);
  for (const event of ["hashchange", "popstate"]) listen(window, event, () => {
    stopTopScroll();
    scheduleUpdate();
  });
  listen(compact, "change", syncLayout);
  const headerObserver = new ResizeObserver(measureHeader);
  headerObserver.observe(header);
  const tableObserver = new ResizeObserver(() => {
    updateTableOverflow();
    scheduleUpdate();
  });
  const table = document.querySelector("#table-wrapper");
  if (table) tableObserver.observe(table);
  renderMenus();
  update();
  measureHeader();

  return () => {
    stopTopScroll();
    removers.forEach(remove => remove());
    headerObserver.disconnect();
    tableObserver.disconnect();
    if (frame) window.cancelAnimationFrame(frame);
  };
}
