const t = (k, v) => window.MetrikI18n.t(k, v);
const esc = (v) => window.MetrikSanitize.escapeHtml(v);
const seg = (v) => window.MetrikSanitize.pathSegment(v);

function setStatus(message = "", tone = "muted") {
  const el = document.getElementById("yield-status");
  if (!el) return;
  el.hidden = !message;
  el.textContent = message;
  el.className = tone === "warn" ? "hint" : "hint";
}

function formatEur(value) {
  if (value == null) return "—";
  return `€${Number(value).toLocaleString()}`;
}

function formatPct(value) {
  if (value == null) return "—";
  return `${Number(value).toFixed(1)}%`;
}

function renderRows(rows) {
  const body = document.getElementById("yield-body");
  if (!body) return;

  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="6">${t("rent_yield_empty")}</td></tr>`;
    setStatus(t("rent_yield_empty_detail"));
    return;
  }

  setStatus("");

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
}

async function loadRentYield() {
  try {
    const res = await fetch("/api/rent-yield");
    if (!res.ok) throw new Error("fetch failed");
    const data = await res.json();
    if (data.cached) {
      setStatus(t("rent_yield_cached"));
    }
    renderRows(data.rows || []);
  } catch {
    const body = document.getElementById("yield-body");
    if (body) body.innerHTML = `<tr><td colspan="6">${t("error_generic")}</td></tr>`;
    setStatus(t("rent_yield_load_error"), "warn");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  window.MetrikI18n.apply();
  if (window.MetrikTrack) {
    window.MetrikTrack.track("rent_yield_viewed", { municipality: "Prishtina" });
  }
  loadRentYield();
});

document.addEventListener("metrik:langchange", () => {
  loadRentYield();
});
