const t = (k, v) => window.MetrikI18n.t(k, v);
const esc = (v) => window.MetrikSanitize.escapeHtml(v);
const seg = (v) => window.MetrikSanitize.pathSegment(v);

let listingType = "rent";
let lastResults = null;
let findLoading = false;
let hasUserInteracted = false;

const BUDGET_BOUNDS = {
  rent: { min: 100, max: 2000, step: 10, default: 500 },
  sale: { min: 20000, max: 500000, step: 1000, default: 120000 },
};

function fmtBudget(value) {
  if (listingType === "rent") {
    return `${window.MetrikFormat.euroRent(value)}${t("per_month_suffix")}`;
  }
  return window.MetrikFormat.euroSale(value);
}

function fmtAreaRange(min, max) {
  const hi = max >= 200 ? "200+" : String(max);
  return `${min}–${hi} m²`;
}

function syncBudgetSlider() {
  const bounds = BUDGET_BOUNDS[listingType];
  const slider = document.getElementById("budget-slider");
  const hidden = document.getElementById("max-budget");
  const out = document.getElementById("budget-slider-out");
  if (!slider || !hidden) return;

  slider.min = String(bounds.min);
  slider.max = String(bounds.max);
  slider.step = String(bounds.step);
  const current = Number(hidden.value);
  const next =
    Number.isFinite(current) && current >= bounds.min && current <= bounds.max
      ? current
      : bounds.default;
  slider.value = String(next);
  hidden.value = String(next);
  if (out) out.textContent = fmtBudget(next);
}

function syncAreaSliders() {
  const minSlider = document.getElementById("min-area-slider");
  const maxSlider = document.getElementById("max-area-slider");
  const minHidden = document.getElementById("min-area");
  const maxHidden = document.getElementById("max-area");
  const out = document.getElementById("area-slider-out");
  if (!minSlider || !maxSlider || !minHidden || !maxHidden) return;

  let minVal = Number(minSlider.value);
  let maxVal = Number(maxSlider.value);
  if (minVal > maxVal) {
    if (document.activeElement === minSlider) {
      maxVal = minVal;
      maxSlider.value = String(maxVal);
    } else {
      minVal = maxVal;
      minSlider.value = String(minVal);
    }
  }

  minHidden.value = String(minVal);
  maxHidden.value = String(maxVal);
  if (out) out.textContent = fmtAreaRange(minVal, maxVal);

  document.querySelectorAll(".find-preset-btn").forEach((btn) => {
    const pMin = Number(btn.dataset.min);
    const pMax = Number(btn.dataset.max || "200");
    const active = minVal === pMin && maxVal === pMax;
    btn.classList.toggle("active", active);
  });
}

function setMode(mode) {
  listingType = mode === "sale" ? "sale" : "rent";
  document.querySelectorAll(".mode-btn").forEach((btn) => {
    const active = btn.dataset.mode === listingType;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  const label = document.getElementById("find-budget-label");
  const suffix = document.getElementById("find-budget-suffix");
  if (label) label.textContent = t(listingType === "rent" ? "find_budget_rent" : "find_budget_sale");
  if (suffix) suffix.textContent = listingType === "rent" ? t("per_month_suffix") : "€";
  const minPsmLabel = document.getElementById("find-min-psm-label");
  const maxPsmLabel = document.getElementById("find-max-psm-label");
  const psmSuffix = document.getElementById("find-psm-suffix");
  const psmSuffixMax = document.getElementById("find-psm-suffix-max");
  if (minPsmLabel) minPsmLabel.textContent = t(listingType === "rent" ? "find_min_psm_rent" : "find_min_psm_sale");
  if (maxPsmLabel) maxPsmLabel.textContent = t(listingType === "rent" ? "find_max_psm_rent" : "find_max_psm_sale");
  const psmUnit = listingType === "rent" ? `€/m²${t("per_month_suffix")}` : "€/m²";
  if (psmSuffix) psmSuffix.textContent = psmUnit;
  if (psmSuffixMax) psmSuffixMax.textContent = psmUnit;
  const minPsm = document.getElementById("min-psm");
  const maxPsm = document.getElementById("max-psm");
  if (minPsm) minPsm.placeholder = listingType === "rent" ? "4" : "800";
  if (maxPsm) maxPsm.placeholder = listingType === "rent" ? "12" : "2000";
  syncBudgetSlider();
}

function fmtPrice(value, { monthly = true } = {}) {
  if (value == null) return "—";
  if (listingType === "rent") {
    return `${window.MetrikFormat.euroRent(value)}${monthly ? t("per_month_suffix") : ""}`;
  }
  return window.MetrikFormat.euroSale(value);
}

function confidenceBadge(level) {
  const safeLevel = window.MetrikSanitize.confidenceClass(level);
  const label = esc(window.MetrikI18n.translateConfidence(safeLevel));
  return `<span class="confidence-badge confidence-${safeLevel}">${label}</span>`;
}

function tierLabel(tier) {
  const key = ["best", "good", "stretch"].includes(tier) ? tier : "good";
  return t(`find_tier_${key}`);
}

function tierClass(tier) {
  const key = ["best", "good", "stretch"].includes(tier) ? tier : "good";
  return `find-tier-${key}`;
}

function displayPrice(row) {
  if (row.estimated_price_eur != null && row.estimated_target_sqm != null) {
    return fmtPrice(row.estimated_price_eur);
  }
  return fmtPrice(row.median_price_eur);
}

function priceLabel(row) {
  if (row.estimated_price_eur != null && row.estimated_target_sqm != null) {
    return t("find_col_estimated", { sqm: Math.round(row.estimated_target_sqm) });
  }
  return t("find_col_median");
}

function valuateHref(row) {
  const params = new URLSearchParams({
    type: listingType,
    neighborhood: row.name,
  });
  if (row.median_area_sqm) params.set("area", String(Math.round(row.estimated_target_sqm || row.median_area_sqm)));
  const beds = document.getElementById("bedrooms")?.value;
  if (beds !== "") params.set("bedrooms", beds);
  return `/valuate?${params.toString()}`;
}

function setPreviewVisible(visible) {
  document.getElementById("find-preview")?.classList.toggle("hidden", !visible);
}

function setSubmitState() {
  const btn = document.getElementById("find-submit");
  if (!btn) return;
  btn.disabled = findLoading;
  btn.textContent = findLoading ? t("find_working") : t("find_submit");
}

function fitBar(score) {
  const pct = Math.max(8, Math.min(100, Number(score) || 0));
  return `<div class="find-fit-bar" role="presentation" aria-hidden="true"><span style="width:${pct}%"></span></div>`;
}

function renderCard(row) {
  const rank = row.rank || "—";
  const tier = row.fit_tier || "good";
  const headroom =
    row.budget_headroom_eur != null
      ? fmtPrice(row.budget_headroom_eur, { monthly: listingType === "rent" })
      : "—";
  const matches = `${row.match_count} (${row.afford_pct}%)`;
  const areaLine = row.estimated_target_sqm
    ? t("find_target_area", { sqm: Math.round(row.estimated_target_sqm) })
    : row.median_area_sqm
      ? window.MetrikFormat.area(row.median_area_sqm)
      : "—";
  const psmLine =
    row.median_price_psm != null && row.median_price_psm > 0
      ? listingType === "rent"
        ? `${window.MetrikFormat.euroRentPsm(row.median_price_psm)}${t("per_month_suffix")}`
        : window.MetrikFormat.euroSalePsm(row.median_price_psm)
      : null;

  return `
    <article class="compare-nh-card find-nh-card ${tierClass(tier)}">
      <div class="find-card-top">
        <span class="find-rank">#${rank}</span>
        <span class="find-tier-badge ${tierClass(tier)}">${tierLabel(tier)}</span>
      </div>
      <div class="compare-nh-card-header">
        <a class="compare-nh-card-name" href="/market/neighborhood/${seg(row.slug)}">${esc(row.name)}</a>
        ${confidenceBadge(row.confidence)}
      </div>
      <p class="find-card-summary">${esc(t(row.summary_key))}</p>
      ${fitBar(row.fit_score)}
      <p class="find-fit-label">${t("find_col_fit")}: <strong>${row.fit_score}</strong>/100</p>
      <dl class="compare-nh-stats">
        <div>
          <dt>${priceLabel(row)}</dt>
          <dd>${displayPrice(row)}</dd>
        </div>
        <div>
          <dt>${t("find_col_matches")}</dt>
          <dd>${matches}</dd>
        </div>
        <div>
          <dt>${t("find_col_headroom")}</dt>
          <dd>${headroom}</dd>
        </div>
        <div>
          <dt>${t("find_col_area")}</dt>
          <dd>${areaLine}</dd>
        </div>
        ${
          psmLine
            ? `<div><dt>${listingType === "rent" ? t("pulse_rent_psm") : t("pulse_sale_psm")}</dt><dd>${psmLine}</dd></div>`
            : ""
        }
        ${
          row.gross_yield_pct != null
            ? `<div><dt>${t("rent_yield_col_yield")}</dt><dd>${row.gross_yield_pct}%</dd></div>`
            : ""
        }
      </dl>
      <div class="find-card-actions">
        <a class="btn-secondary btn-sm" href="/market/neighborhood/${seg(row.slug)}">${esc(t("find_market_link"))}</a>
        <a class="btn-primary btn-sm" href="${esc(valuateHref(row))}">${esc(t("find_valuate_link"))}</a>
      </div>
    </article>
  `;
}

function renderTableRows(rows) {
  const body = document.getElementById("find-results-body");
  if (!body) return;
  body.innerHTML = "";
  for (const row of rows) {
    const tr = document.createElement("tr");
    if (window.MetrikConfidence?.rowClass) {
      tr.className = window.MetrikConfidence.rowClass({ confidence: row.confidence, n: row.match_count });
    }
    tr.innerHTML = `
      <td>${esc(row.rank || "—")}</td>
      <td>
        <a href="/market/neighborhood/${seg(row.slug)}">${esc(row.name)}</a>
        <div class="hint find-row-note">${esc(tierLabel(row.fit_tier || "good"))}</div>
      </td>
      <td><strong>${esc(row.fit_score)}</strong></td>
      <td>${esc(row.match_count)} (${esc(row.afford_pct)}%)</td>
      <td>${esc(displayPrice(row))}</td>
      <td>${row.budget_headroom_pct != null ? `${esc(row.budget_headroom_pct)}%` : "—"}</td>
      <td class="find-actions"><a class="btn-link" href="${esc(valuateHref(row))}">${esc(t("find_valuate_link"))}</a></td>
    `;
    body.appendChild(tr);
  }
}

function renderResults(data) {
  lastResults = data;
  const results = document.getElementById("find-results");
  const empty = document.getElementById("find-empty");
  const error = document.getElementById("find-error");
  const cards = document.getElementById("find-cards");
  const summary = document.getElementById("find-results-summary");

  error?.classList.add("hidden");
  if (!data.neighborhoods?.length) {
    results?.classList.add("hidden");
    empty?.classList.remove("hidden");
    setPreviewVisible(false);
    return;
  }

  empty?.classList.add("hidden");
  results?.classList.remove("hidden");
  setPreviewVisible(false);

  if (summary) {
    const parts = [t("find_results_count", { n: data.neighborhoods.length, total: data.total_matches })];
    if (data.cached) parts.push(t("find_results_cached"));
    summary.textContent = parts.join(" · ");
  }

  if (cards) {
    cards.innerHTML = data.neighborhoods.map((row) => renderCard(row)).join("");
  }
  renderTableRows(data.neighborhoods);
  if (hasUserInteracted) {
    document.getElementById("find-output-col")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function showError(msg) {
  document.getElementById("find-results")?.classList.add("hidden");
  document.getElementById("find-empty")?.classList.add("hidden");
  setPreviewVisible(false);
  const error = document.getElementById("find-error");
  const msgEl = document.getElementById("find-error-msg");
  if (msgEl) msgEl.textContent = msg;
  error?.classList.remove("hidden");
}

async function submitFind(e) {
  if (e) e.preventDefault();
  const budget = Number(document.getElementById("max-budget").value);
  const minAreaRaw = document.getElementById("min-area").value;
  const maxAreaRaw = document.getElementById("max-area").value;
  const minPsmRaw = document.getElementById("min-psm")?.value;
  const maxPsmRaw = document.getElementById("max-psm")?.value;
  const bedsRaw = document.getElementById("bedrooms").value;
  const payload = {
    listing_type: listingType,
    max_budget_eur: budget,
    min_area_sqm: minAreaRaw ? Number(minAreaRaw) : null,
    max_area_sqm: maxAreaRaw ? Number(maxAreaRaw) : null,
    min_price_psm_eur: minPsmRaw ? Number(minPsmRaw) : null,
    max_price_psm_eur: maxPsmRaw ? Number(maxPsmRaw) : null,
    bedrooms: bedsRaw === "" ? null : Number(bedsRaw),
    top_n: 8,
  };

  findLoading = true;
  setSubmitState();
  const hint = document.getElementById("find-hint");
  if (hint) hint.textContent = t("find_working");

  try {
    const res = await fetch("/api/budget-match", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error("request failed");
    const data = await res.json();
    renderResults(data);
    if (window.MetrikTrack) {
      window.MetrikTrack.track("budget_match_completed", {
        listing_type: listingType,
        results_count: data.neighborhoods?.length || 0,
      });
    }
  } catch {
    showError(t("find_error"));
  } finally {
    findLoading = false;
    setSubmitState();
    if (hint) hint.textContent = t("find_hint_live");
  }
}

function applyPreset(min, max) {
  const minSlider = document.getElementById("min-area-slider");
  const maxSlider = document.getElementById("max-area-slider");
  if (minSlider) minSlider.value = String(min);
  if (maxSlider) maxSlider.value = String(max || "200");
  syncAreaSliders();
}

function wireForm() {
  document.querySelectorAll(".mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      setMode(btn.dataset.mode);
    });
  });
  document.getElementById("find-form")?.addEventListener("submit", (e) => {
    hasUserInteracted = true;
    submitFind(e);
  });

  const budgetSlider = document.getElementById("budget-slider");
  budgetSlider?.addEventListener("input", () => {
    const hidden = document.getElementById("max-budget");
    const out = document.getElementById("budget-slider-out");
    const value = Number(budgetSlider.value);
    if (hidden) hidden.value = String(value);
    if (out) out.textContent = fmtBudget(value);
  });

  ["min-area-slider", "max-area-slider"].forEach((id) => {
    document.getElementById(id)?.addEventListener("input", () => {
      syncAreaSliders();
    });
  });

  document.querySelectorAll(".find-preset-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      applyPreset(Number(btn.dataset.min), Number(btn.dataset.max || "200"));
    });
  });
}

function initFromQuery() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("type") === "sale") setMode("sale");
  if (params.get("budget")) {
    const hidden = document.getElementById("max-budget");
    if (hidden) hidden.value = params.get("budget");
    syncBudgetSlider();
  }
  if (params.get("min_area")) {
    const el = document.getElementById("min-area-slider");
    if (el) el.value = params.get("min_area");
  }
  if (params.get("max_area")) {
    const el = document.getElementById("max-area-slider");
    if (el) el.value = params.get("max_area");
  }
  syncAreaSliders();
  if (params.get("min_psm")) document.getElementById("min-psm").value = params.get("min_psm");
  if (params.get("max_psm")) document.getElementById("max-psm").value = params.get("max_psm");
  if (params.get("bedrooms")) document.getElementById("bedrooms").value = params.get("bedrooms");
  if (params.get("budget")) {
    hasUserInteracted = true;
    setTimeout(() => document.getElementById("find-form")?.requestSubmit(), 0);
  }
}

document.addEventListener("metrik:langchange", () => {
  window.MetrikI18n.apply();
  setMode(listingType);
  syncBudgetSlider();
  syncAreaSliders();
  if (lastResults) renderResults(lastResults);
});

wireForm();
setMode("rent");
syncAreaSliders();
setPreviewVisible(true);
setSubmitState();
initFromQuery();
