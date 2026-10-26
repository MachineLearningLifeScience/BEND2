// Horizontal overflow prevents a table's own header from sticking to the page.
// Keep a visual copy aligned with the original, without nesting vertical scroll.
export function initTableHeadings() {
  const wrapper = document.querySelector("#table-wrapper");
  const masthead = document.querySelector(".research-header");
  if (!wrapper || !masthead) return () => {};

  const layer = document.createElement("div");
  layer.className = "table-headings";
  layer.hidden = true;
  // The real table retains its semantic headings and keyboard controls.
  layer.setAttribute("aria-hidden", "true");
  const viewport = document.createElement("div");
  viewport.className = "table-headings-viewport";
  layer.append(viewport);
  document.body.append(layer);

  let table, sourceHead, copy, frame = 0;
  let nearby = false, visible = false, dirty = true;
  let widths = [], headHeight = 0, tableWidth = 0;
  const rendered = {};
  const write = (name, value) => {
    if (rendered[name] !== value) {
      layer.style[name] = value;
      rendered[name] = value;
    }
  };
  function schedule() {
    if (!frame && (nearby || visible || dirty)) frame = requestAnimationFrame(update);
  }
  function refresh() {
    dirty = true;
    schedule();
  }
  function rebuild() {
    if (table) resizeObserver.unobserve(table);
    table = wrapper.querySelector(".results-table");
    sourceHead = table?.tHead;
    viewport.replaceChildren();
    copy = null;
    if (sourceHead) {
      copy = table.cloneNode(false);
      copy.removeAttribute("id");
      const columns = table.querySelector("colgroup");
      if (columns) copy.append(columns.cloneNode(true));
      copy.append(sourceHead.cloneNode(true));
      copy.querySelectorAll("[id]").forEach(node => node.removeAttribute("id"));
      copy.querySelectorAll("[aria-labelledby],[aria-describedby],[aria-controls]").forEach(node => {
        node.removeAttribute("aria-labelledby");
        node.removeAttribute("aria-describedby");
        node.removeAttribute("aria-controls");
      });
      copy.querySelectorAll("button,a,input,select,[tabindex]").forEach(node => node.tabIndex = -1);
      viewport.append(copy);
      resizeObserver.observe(table);
    }
    refresh();
  }
  function update() {
    frame = 0;
    if (!copy || !sourceHead) {
      layer.hidden = true;
      visible = false;
      dirty = false;
      return;
    }
    const bounds = wrapper.getBoundingClientRect();
    const tableBounds = table.getBoundingClientRect();
    const headingBounds = sourceHead.getBoundingClientRect();
    const top = masthead.getBoundingClientRect().bottom;
    const height = window.innerHeight;
    if (dirty) {
      headHeight = headingBounds.height;
      tableWidth = tableBounds.width;
      widths = [...sourceHead.rows[sourceHead.rows.length - 1].cells]
        .map(cell => cell.getBoundingClientRect().width);
    }
    const show = wrapper.scrollWidth > wrapper.clientWidth + 2
      && height >= 600 && height - top - headHeight >= 240
      && headingBounds.top < top && tableBounds.bottom > top;
    if (show) {
      // Let the table's last row push the heading away, as native sticky does.
      write("top", `${Math.min(top, tableBounds.bottom - headHeight)}px`);
      write("left", `${bounds.left}px`);
      write("width", `${wrapper.clientWidth}px`);
    }
    if (dirty) {
      copy.style.width = `${tableWidth}px`;
      [...copy.querySelectorAll("col")].forEach((column, i) => {
        if (widths[i] != null) column.style.width = `${widths[i]}px`;
      });
      dirty = false;
    }
    if (visible !== show) {
      layer.hidden = !show;
      visible = show;
    }
    // Apply after showing: hidden scroll containers cannot retain an offset.
    if (show && Math.abs(viewport.scrollLeft - wrapper.scrollLeft) > .5)
      viewport.scrollLeft = wrapper.scrollLeft;
  }

  // Pointer controls share the document's existing action handlers. Do not put
  // keyboard focus into this hidden-from-AT copy when a heading is clicked.
  const preventFocus = event => {
    if (event.target.closest("button,a")) event.preventDefault();
  };
  const syncFromCopy = () => {
    if (visible && !dirty && Math.abs(wrapper.scrollLeft - viewport.scrollLeft) > .5)
      wrapper.scrollLeft = viewport.scrollLeft;
  };
  layer.addEventListener("pointerdown", preventFocus);
  viewport.addEventListener("scroll", syncFromCopy, { passive: true });
  wrapper.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("scroll", schedule, { passive: true });
  window.addEventListener("resize", refresh, { passive: true });
  const resizeObserver = new ResizeObserver(refresh);
  resizeObserver.observe(wrapper);
  resizeObserver.observe(masthead);
  const changes = new MutationObserver(rebuild);
  changes.observe(wrapper, { childList: true });
  const intersection = new IntersectionObserver(entries => {
    nearby = entries[0].isIntersecting;
    schedule();
  }, { rootMargin: "160px 0px" });
  intersection.observe(wrapper);
  rebuild();

  return () => {
    if (frame) cancelAnimationFrame(frame);
    resizeObserver.disconnect();
    changes.disconnect();
    intersection.disconnect();
    wrapper.removeEventListener("scroll", schedule);
    window.removeEventListener("scroll", schedule);
    window.removeEventListener("resize", refresh);
    layer.remove();
  };
}

initTableHeadings();
