// The panel: back and forward, one box, a close button, and the page.
// Python renders the page (HTML); this script only swaps it in and reports clicks.
export default function (component) {
  const { data, setTriggerValue, parentElement } = component;
  const G = (window.__wrda = window.__wrda || { swaps: 0, calls: 0, mounts: 0, scroll: {}, sent: 0 });
  G.calls += 1;

  let root = parentElement.querySelector(".panel");
  if (!root) {
    G.mounts += 1;
    root = document.createElement("div");
    root.className = "panel";
    root.innerHTML =
      '<div class="head">' +
      '<button class="b back" title="Back: the page this panel showed before">\u2039</button>' +
      '<button class="b fwd" title="Forward">\u203a</button>' +
      '<input class="box" type="text" spellcheck="false" autocomplete="off" autocapitalize="off">' +
      '<button class="b slim" title="Collapse this panel to a strip; it keeps its place in the row">\u2013</button>' +
      '<button class="b close" title="Close this panel">✕</button>' +
      "</div>" +
      '<div class="said" hidden></div>' +
      '<div class="page" tabindex="-1"></div>' +
      '<div class="spine" title="Click to open this panel again"><span class="tw">\u25b8</span><span class="st"></span></div>';
    parentElement.appendChild(root);
    const box = root.querySelector(".box");
    const page = root.querySelector(".page");
    const send = (t, more) => {
      G.sent += 1;
      G.lastSend = performance.now();
      root._send("ev", Object.assign({ t: t, n: G.sent, y: Math.round(page.scrollTop) }, more || {}));
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
    root.querySelector(".spine").addEventListener("click", () => send("thin"));
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
    // called by Streamlit when the panel is closed
    root._cleanup = () => { window.removeEventListener("resize", root._fit); watcher.disconnect(); G.cleanups = (G.cleanups || 0) + 1; };
  }
  root._fit();
  root._send = setTriggerValue;
  root._data = data;
  const box = root.querySelector(".box");
  const page = root.querySelector(".page");
  const said = root.querySelector(".said");
  // distance of an element from the top of the scrolled text
  const where = (el) => page.scrollTop + el.getBoundingClientRect().top - page.getBoundingClientRect().top;

  // a collapsed panel shows only its spine; remember where its page was, to put it back when it is opened
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
  return root._cleanup;
}
