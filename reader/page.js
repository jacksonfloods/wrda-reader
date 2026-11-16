// The panel: back and forward, one box, a close button, and the page.
// Python renders the page (HTML); this script only swaps it in and reports clicks.
//
// A panel is drawn in a column of the page's row. The column and this script's frame in it are kept when
// another panel comes to stand there (a panel was moved or closed, or one was opened beside): the frame is
// handed the new panel and shows it. After a move, every column the move touched is shown in the same instant.
export default function (component) {
  const { data, setTriggerValue, parentElement } = component;
  const G = (window.__wrda = window.__wrda || { swaps: 0, calls: 0, mounts: 0, scroll: {}, sent: 0 });
  G.calls += 1;
  // the column of the page's row that holds a panel
  const columnOf = (el) => {
    const r = el.getRootNode();
    const host = r instanceof ShadowRoot ? r.host : el;
    return host && host.closest ? host.closest('[data-testid="stColumn"]') : null;
  };
  // put a column back where the page lays it out, after a drag shifted it
  const settle = (c) => {
    c.style.transition = "none";
    c.style.transform = "";
    c.style.zIndex = "";
    c.style.position = "";
    requestAnimationFrame(() => { c.style.transition = ""; });
  };
  // a move is finished when every column it touched has been handed its new panel: all are shown together,
  // and in that same instant the columns go back to where the page lays them out
  const finishDrop = (drop) => {
    if (G.dropped !== drop) return;
    G.dropped = null;
    clearTimeout(drop.late);
    clearTimeout(drop.lost);
    drop.waiting.forEach((d, r) => r._show(d));
    drop.cols.forEach(settle);
  };

  let root = parentElement.querySelector(".panel");
  if (!root) {
    G.mounts += 1;
    root = document.createElement("div");
    root.className = "panel";
    root.innerHTML =
      '<div class="head">' +
      '<button class="b back" title="Back: the page this panel showed before">‹</button>' +
      '<button class="b fwd" title="Forward">›</button>' +
      '<input class="box" type="text" spellcheck="false" autocomplete="off" autocapitalize="off">' +
      '<button class="b slim" title="Collapse this panel to a strip; it keeps its place in the row">–</button>' +
      '<button class="b close" title="Close this panel">✕</button>' +
      "</div>" +
      '<div class="said" hidden></div>' +
      '<div class="page" tabindex="-1"></div>' +
      '<div class="spine" title="Click to open this panel again"><span class="tw">▸</span><span class="st"></span></div>';
    parentElement.appendChild(root);
    const box = root.querySelector(".box");
    const page = root.querySelector(".page");
    const said = root.querySelector(".said");
    const send = (t, more) => {
      G.sent += 1;
      G.lastSend = performance.now();
      // the click says which panel it was made in: the frame may be showing another panel by the time it is read
      root._send("ev", Object.assign({ t: t, n: G.sent, id: root._data.id, y: Math.round(page.scrollTop) }, more || {}));
    };
    box.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        send("typed", { text: box.value, beside: !!(e.metaKey || e.ctrlKey) });
        page.focus({ preventScroll: true });     // the keyboard now scrolls the text; the next click in the box selects it all
      }
      else if (e.key === "Escape") { box.value = root._data.box || ""; page.focus({ preventScroll: true }); }
    });
    box.addEventListener("focus", () => box.select());
    root.querySelector(".back").addEventListener("click", () => send("back"));
    root.querySelector(".fwd").addEventListener("click", () => send("fwd"));
    root.querySelector(".close").addEventListener("click", () => send("close"));
    root.querySelector(".slim").addEventListener("click", () => send("thin"));
    // a click on the spine opens the panel again; a drag moves it (below) and is not a click
    root.querySelector(".spine").addEventListener("click", () => { if (performance.now() - (root._dragEnd || 0) > 400) send("thin"); });

    // ---- moving the panel: drag its header (or its spine) sideways, the way a window is dragged by its title bar.
    // The panel follows the pointer and the others slide aside to open its place; on release the reader is told
    // the new place, and it hands every column its panel in the new order.
    const startDrag = (e, handle) => {
      if (e.button !== 0 || G.drag || G.dropped) return;
      const col = columnOf(root);
      const row = col && col.parentElement;                // the row of columns; it scrolls sideways
      if (!row) return;
      const cols = Array.from(row.children).filter((c) => c.matches('[data-testid="stColumn"]'));
      const i0 = cols.indexOf(col);
      if (cols.length < 2 || i0 < 0) return;
      e.preventDefault();                                   // the drag selects no text
      const x0 = e.clientX, sl0 = row.scrollLeft;
      // where every column stands before the drag, measured along the row (so scrolling the row changes nothing)
      const at = cols.map((c) => { const r = c.getBoundingClientRect(); return { left: r.left + sl0, width: r.width }; });
      const gap = Math.max(0, at[1].left - at[0].left - at[0].width);
      const me = at[i0], last = at[at.length - 1];
      const d = (G.drag = { x: x0, to: i0, lifted: false, raf: 0 });
      const place = () => {
        const want = d.x - x0 + row.scrollLeft - sl0;
        const dx = Math.max(at[0].left - me.left, Math.min(last.left + last.width - me.left - me.width, want));   // it stays in the row
        let to = i0;
        cols.forEach((c, j) => {
          if (j === i0) return;
          const mid = at[j].left + at[j].width / 2;
          let shift = 0;                                    // a neighbour gives way once this panel's edge passes its middle
          if (j > i0 && me.left + me.width + dx > mid) { shift = -(me.width + gap); to = Math.max(to, j); }
          if (j < i0 && me.left + dx < mid) { shift = me.width + gap; to = Math.min(to, j); }
          c.style.transform = shift ? "translateX(" + shift + "px)" : "";
        });
        col.style.transform = "translateX(" + dx + "px)";
        d.to = to;
      };
      const nearEdge = () => {                              // near either end of the row, the row scrolls under the panel
        if (G.drag !== d) return;
        const r = row.getBoundingClientRect();
        const v = d.x < r.left + 48 ? -(r.left + 48 - d.x) / 4 : d.x > r.right - 48 ? (d.x - r.right + 48) / 4 : 0;
        if (v) {
          const was = row.scrollLeft;
          row.scrollLeft = was + Math.max(-14, Math.min(14, v < 0 ? Math.floor(v) : Math.ceil(v)));
          if (row.scrollLeft !== was) place();
        }
        d.raf = requestAnimationFrame(nearEdge);
      };
      const move = (ev) => {
        d.x = ev.clientX;
        if (!d.lifted && Math.abs(d.x - x0) > 5) {          // a few pixels of travel make it a drag, not a click
          d.lifted = true;
          root.classList.add("dragging");
          cols.forEach((c) => { c.style.transition = c === col ? "none" : "transform 160ms ease"; });
          col.style.position = "relative";
          col.style.zIndex = "30";
          d.raf = requestAnimationFrame(nearEdge);
        }
        if (d.lifted) place();
      };
      const end = (cancel) => {
        if (G.drag !== d) return;
        G.drag = null;
        cancelAnimationFrame(d.raf);
        handle.removeEventListener("pointermove", move);
        handle.removeEventListener("pointerup", up);
        handle.removeEventListener("pointercancel", stop);
        handle.removeEventListener("lostpointercapture", stop);
        window.removeEventListener("keydown", key, true);
        try { handle.releasePointerCapture(e.pointerId); } catch (err) { /* already let go */ }
        if (!d.lifted) return;                              // it was only a click
        root._dragEnd = performance.now();
        root.classList.remove("dragging");
        const to = cancel ? i0 : d.to;
        let off = 0;                                        // how far its new place is from its old one
        for (let j = i0 + 1; j <= to; j++) off += at[j].width + gap;
        for (let j = to; j < i0; j++) off -= at[j].width + gap;
        if (cancel) cols.forEach((c, j) => { if (j !== i0) c.style.transform = ""; });
        col.style.transition = "transform 160ms ease";
        col.style.transform = "translateX(" + off + "px)";
        if (to === i0) { setTimeout(() => cols.forEach(settle), 180); return; }
        // Every column from the old place to the new one will be handed another panel. Until all of them have
        // theirs they stay as the drag left them, which already looks like the new order.
        const touched = cols.filter((c, j) => j >= Math.min(i0, to) && j <= Math.max(i0, to));
        cols.forEach((c) => { if (touched.indexOf(c) < 0) settle(c); });
        const drop = (G.dropped = { cols: touched, waiting: new Map(), at: performance.now(), late: 0, lost: 0 });
        drop.lost = setTimeout(() => finishDrop(drop), 4000);          // the reader did not answer: as it was
        send("move", { to: to });
      };
      const up = () => end(false);
      const stop = () => end(true);
      const key = (ev) => { if (ev.key === "Escape") { ev.preventDefault(); end(true); } };
      handle.setPointerCapture(e.pointerId);
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", up);
      handle.addEventListener("pointercancel", stop);
      handle.addEventListener("lostpointercapture", stop);
      window.addEventListener("keydown", key, true);
    };
    const head = root.querySelector(".head");
    head.addEventListener("pointerdown", (e) => { if (!e.target.closest("button, input")) startDrag(e, head); });
    const spine = root.querySelector(".spine");
    spine.addEventListener("pointerdown", (e) => startDrag(e, spine));

    // distance of an element from the top of the scrolled text
    const where = (el) => page.scrollTop + el.getBoundingClientRect().top - page.getBoundingClientRect().top;
    let down = null;
    page.addEventListener("mousedown", (e) => { down = [e.clientX, e.clientY]; });
    page.addEventListener("click", (e) => {
      // a drag that selects text is not a click
      if (down && Math.abs(e.clientX - down[0]) + Math.abs(e.clientY - down[1]) > 6) return;
      const el = e.target.closest("[data-fold],[data-open],[data-hit],[data-here],[data-above],[data-more],[data-ev],[data-jump],[data-go]");
      if (!el || !page.contains(el)) return;
      const d = el.dataset;
      if (d.jump !== undefined) {
        const t = page.querySelector("#" + CSS.escape(d.jump));
        if (t) page.scrollTop = where(t) - 34;
      } else if (d.fold !== undefined) send("fold", { a: d.fold, all: !!(e.shiftKey && el.classList.contains("sw")) });
      else if (d.open !== undefined) send("open", { a: d.open });
      else if (d.hit !== undefined) send("hit", { a: d.hit });
      else if (d.here !== undefined) send("here", { a: d.here });
      else if (d.above !== undefined) send("above", { a: d.above });
      else if (d.more !== undefined) send("more", { k: d.more, c: d.n });
      else if (d.ev !== undefined) send(d.ev);
      else if (d.go !== undefined) {
        if (e.metaKey || e.ctrlKey) send("open", { a: d.go, beside: true });
        else send("go", { a: d.go, from: d.from || "" });
      }
    });
    page.addEventListener("scroll", () => { G.scroll[root._data.id] = page.scrollTop; }, { passive: true });
    // the panel reaches from where it stands to the foot of the window
    root._fit = () => { root.style.height = Math.max(260, window.innerHeight - root.getBoundingClientRect().top - 8) + "px"; };
    window.addEventListener("resize", root._fit);
    const watcher = new ResizeObserver(root._fit);
    watcher.observe(document.body);
    // called by Streamlit when the frame is taken away (its place in the row is gone)
    root._cleanup = () => { window.removeEventListener("resize", root._fit); watcher.disconnect(); G.cleanups = (G.cleanups || 0) + 1; };

    // ---- show a panel in this frame: the one it showed before, changed, or another that has come to stand here
    root._show = (data) => {
      if (root._data && root._data.id !== data.id) {      // another panel: it is drawn as a panel is first drawn,
        delete root.dataset.ver;                            // and goes to where its own page was left
        root.dataset.thin = "";
      }
      root._data = data;
      // a collapsed panel shows only its spine, and its column is as narrow as the spine
      const col = columnOf(root);
      if (col) { if (data.thin) col.dataset.wrdaThin = "1"; else delete col.dataset.wrdaThin; }
      // remember where a panel's page was when it is collapsed, to put it back when it is opened
      const wasThin = root.dataset.thin === "1";
      if (data.thin && !wasThin) root._keptY = root.dataset.ver === undefined ? (G.scroll[data.id] || 0) : page.scrollTop;
      root.dataset.thin = data.thin ? "1" : "";
      root.classList.toggle("thin", !!data.thin);
      root.querySelector(".spine .st").textContent = data.spine || "";
      if (root.dataset.ver !== data.ver) {
        const first = root.dataset.ver === undefined;
        const top = page.scrollTop;
        page.innerHTML = data.html;
        root.dataset.ver = data.ver;
        if (data.thin) { /* collapsed: no page is showing */ }
        else if (wasThin) page.scrollTop = root._keptY || 0;                  // opened again: where it was left
        else if (first && G.scroll[data.id]) page.scrollTop = G.scroll[data.id];   // a panel that moved keeps its place
        else if (data.to) {
          const t = page.querySelector("#" + CSS.escape("a-" + data.to));
          if (t) { page.scrollTop = Math.max(0, where(t) - 90); t.classList.add("flash"); }
          else page.scrollTop = 0;
        } else if (data.y != null) page.scrollTop = data.y;      // back or forward: where this page was left
        else if (data.keep) page.scrollTop = top;
        else page.scrollTop = 0;
        G.swaps += 1;
        G.lastSwap = performance.now();
        requestAnimationFrame(() => requestAnimationFrame(() => { G.lastPaint = performance.now(); G.paints = (G.paints || 0) + 1; }));
      }
      const active = parentElement.activeElement || document.activeElement;
      if (active !== box || root.dataset.boxver !== data.boxver) box.value = data.box || "";
      root.dataset.boxver = data.boxver;
      box.placeholder = data.placeholder || "";
      box.title = data.boxhelp || "";
      root.dataset.kind = data.kind;
      if (data.said) { said.textContent = data.said; said.hidden = false; } else { said.hidden = true; }
      root.querySelector(".back").disabled = !data.can_back;
      root.querySelector(".fwd").disabled = !data.can_fwd;
      if (data.focus && root.dataset.focused !== data.focus) {
        root.dataset.focused = data.focus;
        setTimeout(() => { box.focus(); }, 0);
      }
      if (data.reveal && root.dataset.revealed !== data.reveal) {
        root.dataset.revealed = data.reveal;
        setTimeout(() => { root.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" }); }, 0);
      }
    };
  }
  root._fit();
  root._send = setTriggerValue;
  // After a move, the columns it touched wait until each has been handed its new panel, and are then shown
  // together (never before the dropped panel has slid into its place).
  const drop = G.dropped;
  if (drop && drop.cols.indexOf(columnOf(root)) >= 0) {
    drop.waiting.set(root, data);
    if (drop.waiting.size >= drop.cols.length) setTimeout(() => finishDrop(drop), Math.max(0, drop.at + 170 - performance.now()));
    else if (!drop.late) drop.late = setTimeout(() => finishDrop(drop), 700);     // some never came: show what did
    return root._cleanup;
  }
  root._show(data);
  return root._cleanup;
}
