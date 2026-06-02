"use strict";

const api = () => window.pywebview.api;
const SVGNS = "http://www.w3.org/2000/svg";

/* ---------- DOM builders (no innerHTML; text via textContent) ---------- */

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null) continue;
      if (k === "class") el.className = v;
      else el.setAttribute(k, v);
    }
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.appendChild(
      typeof kid === "object" ? kid : document.createTextNode(String(kid)),
    );
  }
  return el;
}

function svgEl(tag, attrs, ...kids) {
  const el = document.createElementNS(SVGNS, tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null) continue;
      el.setAttribute(k, String(v));
    }
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.appendChild(
      typeof kid === "object" ? kid : document.createTextNode(String(kid)),
    );
  }
  return el;
}

function mount(el, ...nodes) {
  while (el.firstChild) el.removeChild(el.firstChild);
  nodes.flat().forEach((n) => {
    if (n != null)
      el.appendChild(
        typeof n === "object" ? n : document.createTextNode(String(n)),
      );
  });
}

function empty(text) {
  return h("div", { class: "empty" }, text);
}

function raf2(fn) {
  requestAnimationFrame(() => requestAnimationFrame(fn));
}

/* ---------- formatting ---------- */

const fmt = (n) => (n || 0).toLocaleString("ru-RU");
const compact = (n) => {
  n = n || 0;
  if (n >= 1e6) return (n / 1e6).toFixed(2).replace(".", ",") + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1).replace(".", ",") + "K";
  return String(n);
};
const pctText = (p) => (p == null ? "—" : p + "%");
const limitColor = (p) =>
  p >= 85 ? "var(--rose)" : p >= 60 ? "var(--warn)" : "var(--haiku)";

/* ---------- icons ---------- */

function svgIcon(opts, children) {
  return svgEl(
    "svg",
    {
      viewBox: "0 0 24 24",
      fill: "none",
      stroke: "currentColor",
      "stroke-width": opts.sw || 2,
      "stroke-linecap": "round",
      "stroke-linejoin": "round",
    },
    ...children,
  );
}

const icons = {
  sun: () =>
    svgIcon({}, [
      svgEl("circle", { cx: 12, cy: 12, r: 4 }),
      svgEl("path", {
        d: "M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
      }),
    ]),
  moon: () =>
    svgIcon({}, [
      svgEl("path", { d: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" }),
    ]),
  refresh: () =>
    svgIcon({}, [
      svgEl("path", { d: "M21 12a9 9 0 1 1-2.64-6.36" }),
      svgEl("path", { d: "M21 3v5h-5" }),
    ]),
  clock: () =>
    svgIcon({}, [
      svgEl("circle", { cx: 12, cy: 12, r: 9 }),
      svgEl("path", { d: "M12 7v5l3 2" }),
    ]),
  chev: () => svgIcon({ sw: 2.2 }, [svgEl("path", { d: "M6 9l6 6 6-6" })]),
  grid: () =>
    svgIcon({}, [
      svgEl("rect", { x: 3, y: 3, width: 8, height: 8, rx: 1.5 }),
      svgEl("rect", { x: 13, y: 3, width: 8, height: 8, rx: 1.5 }),
      svgEl("rect", { x: 3, y: 13, width: 8, height: 8, rx: 1.5 }),
      svgEl("rect", { x: 13, y: 13, width: 8, height: 8, rx: 1.5 }),
    ]),
  history: () =>
    svgIcon({}, [
      svgEl("path", { d: "M3 12a9 9 0 1 0 3-6.7L3 8" }),
      svgEl("path", { d: "M3 4v4h4" }),
      svgEl("path", { d: "M12 8v4l3 2" }),
    ]),
  arrowDown: () =>
    svgIcon({ sw: 2.4 }, [svgEl("path", { d: "M12 5v14M19 12l-7 7-7-7" })]),
  arrowUp: () =>
    svgIcon({ sw: 2.4 }, [svgEl("path", { d: "M12 19V5M5 12l7-7 7 7" })]),
};

function mark() {
  const svg = svgEl("svg", { viewBox: "0 0 40 40" });
  for (let i = 0; i < 12; i++) {
    const a = (i * 30 * Math.PI) / 180;
    svg.appendChild(
      svgEl("line", {
        x1: 20 + Math.cos(a) * 6.5,
        y1: 20 + Math.sin(a) * 6.5,
        x2: 20 + Math.cos(a) * 16.5,
        y2: 20 + Math.sin(a) * 16.5,
        stroke: "var(--clay)",
        "stroke-width": 2.4,
        "stroke-linecap": "round",
      }),
    );
  }
  return h("div", { class: "mark" }, svg);
}

/* ---------- tooltip ---------- */

let tipEl = null;

function showTip(target, content) {
  if (!tipEl) return;
  while (tipEl.firstChild) tipEl.removeChild(tipEl.firstChild);
  content.flat().forEach((n) => {
    if (n == null) return;
    tipEl.appendChild(
      typeof n === "object" ? n : document.createTextNode(String(n)),
    );
  });
  tipEl.classList.add("show");
  const r = target.getBoundingClientRect();
  const w = tipEl.offsetWidth;
  const ht = tipEl.offsetHeight;
  let left = r.left + r.width / 2 - w / 2;
  left = Math.max(8, Math.min(left, window.innerWidth - w - 8));
  let top = r.top - ht - 9;
  if (top < 8) top = r.bottom + 13;
  tipEl.style.left = left + "px";
  tipEl.style.top = top + "px";
}

function hideTip() {
  if (tipEl) tipEl.classList.remove("show");
}

function attachTip(el, builder) {
  el.addEventListener("mouseenter", () => showTip(el, builder()));
  el.addEventListener("mouseleave", hideTip);
}

/* ---------- state / refs ---------- */

const state = {
  theme: "light",
  tab: "overview",
  period: "day",
  span: 7,
  open: true,
  spinning: false,
  rings: null,
  tokens: null,
  history: null,
  updatedAt: null,
};
const els = {};

/* ---------- header / skeleton ---------- */

function themeIcon() {
  return state.theme === "light" ? icons.moon() : icons.sun();
}

function tabButton(name, iconNode, label) {
  const b = h("button", null, iconNode, label);
  b.addEventListener("click", () => setTab(name));
  return b;
}

function build() {
  const root = document.getElementById("root");

  els.refreshBtn = h(
    "button",
    { class: "iconbtn", title: "Обновить", "aria-label": "Обновить" },
    icons.refresh(),
  );
  els.refreshBtn.addEventListener("click", onRefreshUsage);
  els.themeBtn = h(
    "button",
    { class: "iconbtn", title: "Тема", "aria-label": "Сменить тему" },
    themeIcon(),
  );
  els.themeBtn.addEventListener("click", toggleTheme);

  const hdr = h(
    "div",
    { class: "hdr" },
    mark(),
    h(
      "div",
      { class: "hdr-titles" },
      h("span", { class: "t1" }, h("em", null, "Claude"), " Usage"),
      h("span", { class: "t2" }, "Max · текущая сессия"),
    ),
    els.refreshBtn,
    els.themeBtn,
  );

  els.tabOverview = tabButton("overview", icons.grid(), "Обзор");
  els.tabHistory = tabButton("history", icons.history(), "История");
  const tabs = h("div", { class: "tabs" }, els.tabOverview, els.tabHistory);

  els.ringsWrap = h("div", { id: "rings-wrap" });
  els.tokensWrap = h("div", { id: "tokens-wrap" });
  els.overview = h("div", { id: "overview" }, els.ringsWrap, els.tokensWrap);
  els.history = h("div", { id: "history", style: "display:none" });

  els.updText = document.createTextNode("Обновлено …");
  const ftr = h(
    "div",
    { class: "ftr" },
    h("span", { class: "upd" }, h("span", { class: "pulse" }), els.updText),
    h("span", { class: "plan" }, "Max"),
  );

  mount(
    root,
    h("div", { class: "widget" }, hdr, tabs, els.overview, els.history, ftr),
  );

  tipEl = h("div", { class: "tip" });
  document.body.appendChild(tipEl);
}

/* ---------- rings ---------- */

function ringNode({ pct, size, stroke, color, label, sub, big, tip }) {
  const rad = (size - stroke) / 2;
  const c = 2 * Math.PI * rad;
  const off = c * (1 - (pct || 0) / 100);
  const prog = svgEl("circle", {
    class: "prog",
    cx: size / 2,
    cy: size / 2,
    r: rad,
    fill: "none",
    "stroke-width": stroke,
    stroke: color,
    "stroke-dasharray": c,
    "stroke-dashoffset": c,
  });
  const svg = svgEl(
    "svg",
    { width: size, height: size },
    svgEl("circle", {
      class: "track",
      cx: size / 2,
      cy: size / 2,
      r: rad,
      fill: "none",
      "stroke-width": stroke,
    }),
    prog,
  );
  raf2(() => prog.setAttribute("stroke-dashoffset", off));

  const pctSpan = h(
    "span",
    { class: "ring-pct", style: big ? "color:" + color : null },
    pct == null ? "—" : String(pct),
    pct == null
      ? null
      : h("span", { style: "font-size:" + (big ? 15 : 11) + "px" }, "%"),
  );
  const center = h(
    "div",
    { class: "ring-center" },
    pctSpan,
    sub ? h("span", { class: "ring-sub" }, sub) : null,
  );
  const el = h(
    "div",
    { class: "ring " + (big ? "big" : "sm") },
    svg,
    center,
    h("span", { class: "ring-label" }, label),
  );
  if (tip) attachTip(el, tip);
  return el;
}

function renderRings() {
  const r = state.rings || {};
  const grid = h(
    "div",
    { class: "rings" },
    ringNode({
      pct: r.session,
      size: 104,
      stroke: 11,
      color: "var(--clay)",
      label: "Сессия",
      sub: "5 часов",
      big: true,
      tip: () => [
        h("span", { class: "k" }, pctText(r.session)),
        " 5-часового окна израсходовано",
      ],
    }),
    ringNode({
      pct: r.all,
      size: 78,
      stroke: 9,
      color: "var(--sonnet)",
      label: "Все модели",
      tip: () => [
        "Недельный лимит (все модели): ",
        h("span", { class: "k" }, pctText(r.all)),
      ],
    }),
    ringNode({
      pct: r.sonnet,
      size: 78,
      stroke: 9,
      color: "var(--haiku)",
      label: "Sonnet",
      tip: () => [
        "Недельный лимит (Sonnet): ",
        h("span", { class: "k" }, pctText(r.sonnet)),
      ],
    }),
  );
  const reset = h(
    "div",
    { class: "reset" },
    icons.clock(),
    " Лимиты обновлены ",
    h("b", null, r.updated || "—"),
  );
  mount(els.ringsWrap, grid, reset);
}

/* ---------- tokens ---------- */

function segBtn(label, on, fn) {
  const b = h("button", { class: on ? "on" : null }, label);
  b.addEventListener("click", fn);
  return b;
}

function tile({ cap, dot, arrow, num, total, tip }) {
  const capEl = total
    ? h("div", { class: "cap" }, cap)
    : h(
        "div",
        { class: "cap" },
        h("span", { class: "dotline", style: "background:" + dot }),
        cap,
        h("span", { style: "display:inline-flex;width:11px" }, arrow),
      );
  const el = h(
    "div",
    { class: "tile" + (total ? " total" : "") },
    capEl,
    h("div", { class: "num" }, compact(num)),
    h("div", { class: "unit" }, fmt(num) + " ткн"),
  );
  if (tip) attachTip(el, tip);
  return el;
}

function modelRow(m, maxM) {
  const bar = h("i", { style: "width:0;background:" + m.color });
  const el = h(
    "div",
    { class: "mrow" },
    h("span", { class: "mdot", style: "background:" + m.color }),
    h(
      "div",
      { class: "mname" },
      h(
        "div",
        { class: "top" },
        h("span", { class: "nm" }, m.name),
        h("span", { class: "rq" }, fmt(m.req) + " запр."),
      ),
      h("div", { class: "mbar" }, bar),
    ),
    h(
      "div",
      { class: "mval" },
      h("div", { class: "tk" }, compact(m.total)),
      h("div", { class: "io" }, compact(m.in) + " / " + compact(m.out)),
    ),
  );
  raf2(() => (bar.style.width = (m.total / maxM) * 100 + "%"));
  attachTip(el, () => [
    h("span", { class: "k" }, m.name),
    h("br"),
    fmt(m.req) + " запросов · " + fmt(m.total) + " токенов",
  ]);
  return el;
}

function renderExpandLabel() {
  mount(
    els.expand,
    state.open ? "Свернуть детали" : "Показать модели",
    icons.chev(),
  );
}

function toggleModels() {
  state.open = !state.open;
  els.expand.classList.toggle("open", state.open);
  renderExpandLabel();
  if (state.open) {
    els.models.classList.remove("collapsed");
    els.models.style.maxHeight = els.models.scrollHeight + "px";
  } else {
    els.models.style.maxHeight = els.models.scrollHeight + "px";
    void els.models.offsetHeight;
    els.models.classList.add("collapsed");
  }
}

function renderTokens() {
  const t = state.tokens || { in: 0, out: 0, total: 0, models: [] };

  const seg = h(
    "div",
    { class: "seg" },
    segBtn("Сегодня", state.period === "day", () => setPeriod("day")),
    segBtn("Неделя", state.period === "week", () => setPeriod("week")),
  );
  const secHead = h(
    "div",
    { class: "sec-head" },
    h("span", { class: "lbl" }, "Токены"),
    seg,
  );

  const tiles = h(
    "div",
    { class: "tiles" },
    tile({
      cap: "Входные",
      dot: "var(--sonnet)",
      arrow: icons.arrowDown(),
      num: t.in,
      tip: () => ["Входные токены: ", h("span", { class: "k" }, fmt(t.in))],
    }),
    tile({
      cap: "Выходные",
      dot: "var(--haiku)",
      arrow: icons.arrowUp(),
      num: t.out,
      tip: () => ["Выходные токены: ", h("span", { class: "k" }, fmt(t.out))],
    }),
    tile({
      cap: "Всего",
      total: true,
      num: t.total,
      tip: () => [
        "Всего за период: ",
        h("span", { class: "k" }, fmt(t.total)),
        " токенов",
      ],
    }),
  );

  const models = t.models || [];
  els.models = h("div", { class: "models" + (state.open ? "" : " collapsed") });
  if (!models.length) {
    mount(els.models, empty("Пока нет активности."));
  } else {
    const maxM = Math.max(...models.map((m) => m.total), 1);
    const head = h(
      "div",
      { class: "sec-head", style: "margin-bottom:4px" },
      h("span", { class: "lbl" }, "Модели"),
      h(
        "span",
        { class: "lbl", style: "color:var(--ink-3);letter-spacing:.02em" },
        "токены · вход / выход",
      ),
    );
    mount(els.models, head, ...models.map((m) => modelRow(m, maxM)));
  }

  els.expand = h("button", { class: "expand" + (state.open ? " open" : "") });
  els.expand.addEventListener("click", toggleModels);
  renderExpandLabel();

  mount(els.tokensWrap, secHead, tiles, els.models, els.expand);
  if (state.open) els.models.style.maxHeight = els.models.scrollHeight + "px";
}

/* ---------- history ---------- */

function hcard(cl, cv, cu) {
  return h(
    "div",
    { class: "c" },
    h("div", { class: "cl" }, cl),
    h("div", { class: "cv" }, cv),
    h("div", { class: "cu" }, cu),
  );
}

function legendItem(color, label) {
  return h("span", null, h("i", { style: "background:" + color }), label);
}

function barCol(r, today, maxTotal, chartH) {
  const tot = r.in + r.out;
  const inH = (r.in / maxTotal) * chartH;
  const outH = (r.out / maxTotal) * chartH;
  const segOut = h("div", {
    class: "seg",
    style: "height:0;background:var(--clay)",
  });
  const segIn = h("div", {
    class: "seg",
    style: "height:0;background:var(--sonnet)",
  });
  const stack = h("div", { class: "bstack" }, segOut, segIn);
  const el = h(
    "div",
    { class: "bcol" + (today ? " today" : "") },
    stack,
    h("span", { class: "blabel" }, r.d.slice(0, 2)),
  );
  raf2(() => {
    segOut.style.height = outH + "px";
    segIn.style.height = inH + "px";
  });
  attachTip(el, () => [
    h("span", { class: "k" }, r.d),
    " · " + fmt(tot) + " ткн",
    h("br"),
    "вход " + compact(r.in) + " · выход " + compact(r.out),
  ]);
  return el;
}

function limCol(r, limH) {
  const p = r.limit;
  const hgt = p == null ? 3 : Math.max((p / 100) * limH, 3);
  const color = p == null ? "var(--track)" : limitColor(p);
  const bar = h("div", {
    class: "lbar",
    style: "height:0;background:" + color,
  });
  const el = h("div", { class: "lcol" }, bar);
  raf2(() => (bar.style.height = hgt + "px"));
  attachTip(el, () =>
    p == null
      ? [h("span", { class: "k" }, r.d), " · нет данных лимита"]
      : [
          h("span", { class: "k" }, r.d),
          " · пик лимита ",
          h("span", { class: "k" }, p + "%"),
        ],
  );
  return el;
}

function renderHistory() {
  const rows = state.history || [];
  if (!rows.length) {
    mount(els.history, empty("История накапливается по дням."));
    return;
  }

  const sum = rows.reduce((s, r) => s + r.in + r.out, 0);
  const avg = Math.round(sum / rows.length);
  let peak = rows[0];
  for (const r of rows) if (r.in + r.out > peak.in + peak.out) peak = r;

  const hsum = h(
    "div",
    { class: "hsum" },
    hcard("Σ за период", compact(sum), fmt(sum) + " ткн"),
    hcard("Ср./день", compact(avg), "токенов в день"),
    hcard("Пик", compact(peak.in + peak.out), peak.d),
  );

  const chartH = 116;
  const maxTotal = Math.max(...rows.map((r) => r.in + r.out), 1);
  const tokHead = h(
    "div",
    { class: "csec-head" },
    h("span", { class: "lbl" }, "Токены по дням"),
    h(
      "div",
      { class: "seg" },
      segBtn("7д", state.span === 7, () => setSpan(7)),
      segBtn("14д", state.span === 14, () => setSpan(14)),
    ),
  );
  const tokLegend = h(
    "div",
    { class: "legend" },
    legendItem("var(--sonnet)", "Входные"),
    legendItem("var(--clay)", "Выходные"),
  );
  const bars = h(
    "div",
    { class: "bars" },
    rows.map((r, i) => barCol(r, i === rows.length - 1, maxTotal, chartH)),
  );
  const tokSec = h("div", { class: "csec" }, tokHead, tokLegend, bars);

  const limH = 56;
  const limHead = h(
    "div",
    { class: "csec-head" },
    h("span", { class: "lbl" }, "Лимиты по дням"),
    h("span", { class: "lbl", style: "letter-spacing:.02em" }, "пиковый %"),
  );
  const thresh = h(
    "div",
    { class: "thresh", style: "bottom:" + (80 / 100) * limH + "px" },
    h("span", null, "80%"),
  );
  const lim = h(
    "div",
    { class: "lim" },
    thresh,
    ...rows.map((r) => limCol(r, limH)),
  );
  const limLegend = h(
    "div",
    { class: "legend", style: "margin-top:11px" },
    legendItem("var(--haiku)", "<60%"),
    legendItem("var(--warn)", "60–84%"),
    legendItem("var(--rose)", "≥85%"),
  );
  const limSec = h("div", { class: "csec" }, limHead, lim, limLegend);

  mount(els.history, hsum, tokSec, limSec);
}

/* ---------- actions ---------- */

function setTab(name) {
  state.tab = name;
  els.tabOverview.className = name === "overview" ? "on" : "";
  els.tabHistory.className = name === "history" ? "on" : "";
  els.overview.style.display = name === "overview" ? "" : "none";
  els.history.style.display = name === "history" ? "" : "none";
  if (name === "history") loadHistory(state.span);
}

async function setPeriod(p) {
  if (state.period === p) return;
  state.period = p;
  try {
    state.tokens = await api().get_tokens(p);
  } catch (e) {
    console.error(e);
  }
  renderTokens();
}

async function setSpan(s) {
  if (state.span === s) return;
  state.span = s;
  await loadHistory(s);
}

async function loadHistory(span) {
  try {
    state.history = await api().get_history_data(span);
  } catch (e) {
    console.error(e);
  }
  renderHistory();
}

async function refreshTokens() {
  try {
    state.tokens = await api().get_tokens(state.period);
    renderTokens();
    state.updatedAt = new Date();
    updateAgo();
  } catch (e) {
    console.error(e);
  }
}

async function onRefreshUsage() {
  if (state.spinning) return;
  state.spinning = true;
  els.refreshBtn.classList.add("spin");
  els.refreshBtn.disabled = true;
  try {
    const r = await api().refresh_usage();
    if (r) {
      state.rings = r;
      if (r.error) console.warn("usage refresh error:", r.error);
    }
    renderRings();
    state.updatedAt = new Date();
    updateAgo();
  } catch (e) {
    console.error(e);
  } finally {
    state.spinning = false;
    els.refreshBtn.disabled = false;
    setTimeout(() => els.refreshBtn.classList.remove("spin"), 700);
  }
}

function toggleTheme() {
  state.theme = state.theme === "light" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", state.theme);
  try {
    localStorage.setItem("cuw-theme", state.theme);
  } catch (e) {
    /* ignore */
  }
  mount(els.themeBtn, themeIcon());
}

function updateAgo() {
  if (!els.updText) return;
  if (!state.updatedAt) {
    els.updText.nodeValue = "Обновлено …";
    return;
  }
  const s = Math.floor((Date.now() - state.updatedAt.getTime()) / 1000);
  let txt;
  if (s < 5) txt = "только что";
  else if (s < 60) txt = s + " сек назад";
  else txt = Math.floor(s / 60) + " мин назад";
  els.updText.nodeValue = "Обновлено " + txt;
}

/* ---------- boot ---------- */

async function boot() {
  try {
    state.theme = localStorage.getItem("cuw-theme") || "light";
  } catch (e) {
    state.theme = "light";
  }
  document.documentElement.setAttribute("data-theme", state.theme);

  build();
  setTab("overview");

  try {
    const [rings, toks] = await Promise.all([
      api().get_rings(),
      api().get_tokens("day"),
    ]);
    state.rings = rings;
    state.tokens = toks;
  } catch (e) {
    console.error(e);
  }
  renderRings();
  renderTokens();
  state.updatedAt = new Date();
  updateAgo();

  setInterval(refreshTokens, 30000);
  setInterval(updateAgo, 5000);
}

window.addEventListener("pywebviewready", boot);
