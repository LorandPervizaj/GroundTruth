const t = (k, v) => window.MetrikI18n.t(k, v);
const esc = (v) => window.MetrikSanitize.escapeHtml(v);
const seg = (v) => window.MetrikSanitize.pathSegment(v);

const YIELD_CHART_TOP = 10;
let lastYieldRows = [];
let yieldShowAll = false;

function setStatus(message = "", tone = "muted") {
  const el = document.getElementById("yield-status");
  if (!el) return;
  el.hidden = !message;
  el.textContent = message;
  el.className = tone === "warn" ? "hint" : "hint";
}

function setRetryVisible(visible) {
  const wrap = document.getElementById("yield-retry-wrap");
  if (wrap) wrap.classList.toggle("hidden", !visible);
}

function formatEur(value) {
  if (value == null) return "—";
  return `€${Number(value).toLocaleString()}`;
}

function formatPct(value) {
  if (value == null) return "—";
  return `${Number(value).toFixed(1)}%`;
}

function rankedRows(rows) {
  return [...(rows || [])]
    .filter((r) => r.gross_yield_pct != null && Number.isFinite(Number(r.gross_yield_pct)))
    .sort((a, b) => Number(b.gross_yield_pct) - Number(a.gross_yield_pct));
}

async function renderYieldChart(rows) {
  const section = document.getElementById("yield-chart-section");
  const canvas = document.getElementById("yieldRankChart");
  const wrap = document.getElementById("yield-chart-wrap");
  const note = document.getElementById("yield-chart-note");
  const toggle = document.getElementById("yield-chart-toggle");
  const charts = window.MetrikCharts;
  if (!section || !canvas || !charts) return;

  const ranked = rankedRows(rows);
  if (!ranked.length) {
    section.hidden = true;
    charts.destroy(canvas);
    return;
  }

  section.hidden = false;
  const visible = yieldShowAll ? ranked : ranked.slice(0, YIELD_CHART_TOP);
  if (toggle) {
    const extra = ranked.length > YIELD_CHART_TOP;
    toggle.hidden = !extra;
    if (extra) {
      toggle.textContent = yieldShowAll
        ? t("rent_yield_chart_show_top", { n: YIELD_CHART_TOP })
        : t("rent_yield_chart_show_all", { n: ranked.length });
    }
  }

  await charts.ensureChartJs();
  charts.showChart(wrap);
  const labels = visible.map((r) => r.neighborhood_name || "—");
  const values = visible.map((r) => Number(r.gross_yield_pct));
  charts.createHorizontalBarChart(canvas, {
    labels,
    values,
    label: t("rent_yield_col_yield"),
    formatTick: (v) => `${Number(v).toFixed(1)}%`,
    tooltipBuilder: (items) => {
      const idx = items[0]?.dataIndex ?? 0;
      const row = visible[idx];
      if (!row) return { title: "", lines: [] };
      return {
        title: row.neighborhood_name || "—",
        lines: [
          `${t("rent_yield_col_yield")}: ${formatPct(row.gross_yield_pct)}`,
          `${t("rent_yield_col_rent_n")}: ${row.rent_listings ?? "—"}`,
          `${t("rent_yield_col_sale_n")}: ${row.sale_listings ?? "—"}`,
          t("rent_yield_chart_disclaimer"),
        ],
      };
    },
  });
  charts.setNote(note, t("rent_yield_chart_note", { n: visible.length, total: ranked.length }));
}

function renderRows(rows) {
  const body = document.getElementById("yield-body");
  if (!body) return;
  body.removeAttribute("aria-busy");
  lastYieldRows = rows || [];

  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="6">${t("rent_yield_empty")}</td></tr>`;
    setStatus(t("rent_yield_empty_detail"));
    setRetryVisible(false);
    renderYieldChart([]);
    return;
  }

  setStatus("");
  setRetryVisible(false);

  body.innerHTML = rows
    .map((row) => {
      const slug = row.slug ? `/market/neighborhood/${seg(row.slug)}` : "#";
      const name = row.neighborhood_name || "—";
      return `<tr>
        <td><a href="${esc(slug)}">${esc(name)}</a></td>
        <td>${esc(formatPct(row.gross_yield_pct))}</td>
        <td>${esc(formatEur(row.median_rent_eur))}</td>
        <td>${esc(formatEur(row.median_sale_eur))}</td>
        <td>${esc(row.rent_listings ?? "—")}</td>
        <td>${esc(row.sale_listings ?? "—")}</td>
      </tr>`;
    })
    .join("");
  body.classList.add("content-fade-in");
  renderYieldChart(rows);
}

async function loadRentYield() {
  const body = document.getElementById("yield-body");
  if (body) body.setAttribute("aria-busy", "true");
  try {
    const data = window.MetrikApiCache
      ? await window.MetrikApiCache.getJson("/api/rent-yield", { ttlMs: 60_000 })
      : await (await fetch("/api/rent-yield")).json();
    if (data.cached) {
      setStatus(t("rent_yield_cached"));
    }
    renderRows(data.rows || []);
  } catch {
    if (body) {
      body.removeAttribute("aria-busy");
      body.innerHTML = `<tr><td colspan="6">${t("error_generic")}</td></tr>`;
    }
    setStatus(t("rent_yield_load_error"), "warn");
    setRetryVisible(true);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  window.MetrikI18n.apply();
  if (window.MetrikTrack) {
    window.MetrikTrack.track("rent_yield_viewed", { municipality: "Prishtina" });
  }
  document.getElementById("yield-chart-toggle")?.addEventListener("click", () => {
    yieldShowAll = !yieldShowAll;
    renderYieldChart(lastYieldRows);
  });
  document.getElementById("yield-retry")?.addEventListener("click", () => {
    setRetryVisible(false);
    loadRentYield();
  });
  loadRentYield();
});

document.addEventListener("metrik:langchange", () => {
  loadRentYield();
});
