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
  body.removeAttribute("aria-busy");

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
  body.classList.add("content-fade-in");
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
