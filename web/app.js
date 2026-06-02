"use strict";

const api = () => window.pywebview.api;

/* ---------- tiny DOM builder (no innerHTML; text set via textContent) ---------- */

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

function mount(el, ...nodes) {
  while (el.firstChild) el.removeChild(el.firstChild);
  nodes.flat().forEach((n) => {
    if (n != null) el.appendChild(n);
  });
}

function empty(text) {
  return h("div", { class: "empty" }, text);
}

/* ---------- formatting ---------- */

function fmt(n) {
  return (n || 0).toLocaleString("ru-RU");
}

function compact(n) {
  n = n || 0;
  if (n >= 1e9) return (n / 1e9).toFixed(2) + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(2) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return String(n);
}

function pctNum(s) {
  if (s == null) return null;
  const m = String(s).match(/(\d+)/);
  return m ? parseInt(m[1], 10) : null;
}

function level(p) {
  if (p == null) return "";
  if (p >= 80) return "lvl-bad";
  if (p >= 50) return "lvl-warn";
  return "lvl-good";
}

const MODEL_COLORS = {};
const PALETTE = [
  "#d97757",
  "#5b8def",
  "#4caf7d",
  "#e0b450",
  "#a979e0",
  "#56b6c2",
];
function modelColor(name) {
  if (!(name in MODEL_COLORS)) {
    MODEL_COLORS[name] =
      PALETTE[Object.keys(MODEL_COLORS).length % PALETTE.length];
  }
  return MODEL_COLORS[name];
}

function shortModel(name) {
  return String(name)
    .replace(/^claude-/, "")
    .replace(/-\d{8}$/, "");
}

/* ---------- TODAY ---------- */

function renderUsage(data) {
  const box = document.getElementById("gauges");
  const keys = (data && data.keys) || [];
  const latest = data && data.latest;
  if (!latest) {
    mount(box, empty("Нет данных. Нажмите «Обновить»."));
    document.getElementById("usage-updated").textContent = "—";
    return;
  }
  const gauges = keys.map((k) => {
    const p = pctNum(latest[k]);
    const w = p == null ? 0 : Math.min(p, 100);
    return h(
      "div",
      { class: "gauge" },
      h(
        "div",
        { class: "g-top" },
        h("span", null, k),
        h("span", { class: "g-pct" }, latest[k] == null ? "N/A" : latest[k]),
      ),
      h(
        "div",
        { class: "bar " + level(p) },
        h("span", { style: "width:" + w + "%" }),
      ),
    );
  });
  mount(box, gauges);
  document.getElementById("usage-updated").textContent =
    ((latest["Дата"] || "") + " " + (latest["Время"] || "")).trim() || "—";
}

function card(label, value, sub, cls) {
  return h(
    "div",
    { class: "card" + (cls ? " " + cls : "") },
    h("div", { class: "c-label" }, label),
    h("div", { class: "c-value" }, compact(value)),
    h("div", { class: "c-sub" }, sub),
  );
}

function renderTokens(d) {
  document.getElementById("day-label").textContent =
    d && d.day ? "день с 09:00 · " + d.day : "";

  mount(
    document.getElementById("token-cards"),
    card("Входные", d.input, fmt(d.input)),
    card("Выходные", d.output, fmt(d.output)),
    card("Cache read", d.cache_read, fmt(d.cache_read)),
    card("Cache create", d.cache_creation, fmt(d.cache_creation)),
    card(
      "Всего токенов",
      d.total,
      fmt(d.total) +
        " · in+out: " +
        fmt(d.narrow) +
        " · " +
        d.messages +
        " ответов",
      "total",
    ),
  );

  const models = Object.entries(d.byModel || {}).sort(
    (a, b) => b[1].total - a[1].total,
  );
  const mbox = document.getElementById("token-models");
  if (!models.length) {
    mount(mbox, empty("Пока нет активности."));
    return;
  }
  mount(
    mbox,
    models.map(([name, m]) =>
      h(
        "div",
        { class: "model-row" },
        h(
          "div",
          { class: "m-name" },
          h("span", { class: "dot", style: "background:" + modelColor(name) }),
          shortModel(name),
        ),
        h(
          "div",
          { style: "text-align:right" },
          h("div", { class: "m-val" }, compact(m.total)),
          h(
            "div",
            { class: "m-sub" },
            "in " +
              compact(m.input) +
              " · out " +
              compact(m.output) +
              " · " +
              m.messages +
              " отв.",
          ),
        ),
      ),
    ),
  );
}

async function refreshToday() {
  try {
    const [tok, use] = await Promise.all([
      api().get_token_today(),
      api().get_usage_latest(),
    ]);
    renderTokens(tok);
    renderUsage(use);
  } catch (e) {
    console.error(e);
  }
}

async function onRefreshUsage() {
  const btn = document.getElementById("refresh-usage");
  btn.disabled = true;
  const old = btn.textContent;
  btn.textContent = "…";
  try {
    const use = await api().refresh_usage();
    renderUsage(use);
    if (use && use.error) console.warn("usage refresh error:", use.error);
  } catch (e) {
    console.error(e);
  } finally {
    btn.disabled = false;
    btn.textContent = old;
  }
}

/* ---------- HISTORY ---------- */

function tableRow(tag, cells, aligns) {
  return h(
    "tr",
    null,
    cells.map((c, i) =>
      h(
        tag,
        aligns && aligns[i] ? { style: "text-align:" + aligns[i] } : null,
        c,
      ),
    ),
  );
}

function renderTokenHistory(rows) {
  const box = document.getElementById("hist-tokens");
  if (!rows || !rows.length) {
    mount(box, empty("История накапливается по дням."));
    return;
  }
  const head = tableRow("th", ["Дата", "Всего", "Вход", "Выход", "Модели"]);
  const body = rows.map((d) =>
    tableRow(
      "td",
      [
        d.day,
        compact(d.total),
        compact(d.input),
        compact(d.output),
        Object.keys(d.byModel || {})
          .map(shortModel)
          .join(", "),
      ],
      [null, null, null, null, "left"],
    ),
  );
  mount(box, h("table", null, head, ...body));
}

function renderUsageHistory(data) {
  const box = document.getElementById("hist-usage");
  const rows = (data && data.rows) || [];
  const keys = (data && data.keys) || [];
  if (!rows.length) {
    mount(box, empty("Нет записей."));
    return;
  }
  const head = tableRow("th", [
    "Дата",
    ...keys.map((k) => k.replace("Weekly ", "")),
  ]);
  const body = rows.map((r) =>
    tableRow("td", [
      r["Дата"] || "",
      ...keys.map((k) => (r[k] == null ? "—" : r[k])),
    ]),
  );
  mount(box, h("table", null, head, ...body));
}

async function refreshHistory() {
  try {
    const [tok, use] = await Promise.all([
      api().get_token_history(),
      api().get_usage_history(),
    ]);
    renderTokenHistory(tok);
    renderUsageHistory(use);
  } catch (e) {
    console.error(e);
  }
}

/* ---------- tabs / boot ---------- */

function setupTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document
        .querySelectorAll(".tab")
        .forEach((t) => t.classList.remove("active"));
      document
        .querySelectorAll(".tabpane")
        .forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById("tab-" + tab.dataset.tab).classList.add("active");
      if (tab.dataset.tab === "history") refreshHistory();
    });
  });
}

function boot() {
  setupTabs();
  document
    .getElementById("refresh-usage")
    .addEventListener("click", onRefreshUsage);
  refreshToday();
  setInterval(refreshToday, 30000);
}

window.addEventListener("pywebviewready", boot);
