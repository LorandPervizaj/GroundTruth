const t = (k, v) => window.MetrikI18n.t(k, v);
const esc = (v) => window.MetrikSanitize.escapeHtml(v);

const MAX_NEIGHBORHOODS = 3;
const MIN_NEIGHBORHOODS = 2;
const DEFAULT_PICKERS = 3;

let marketOptions = [];
let marketsReady = false;
let marketsLoading = false;
let compareLoading = false;
let lastCompareData = null;

function parseUrlSlugs() {
  const params = new URLSearchParams(window.location.search);
  const raw = params.get("n") || params.get("neighborhoods") || "";
  const fromList = raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, MAX_NEIGHBORHOODS);
  if (fromList.length) {
    return fromList.map((token) => resolveSlugToken(token) || token.toLowerCase());
  }
  const single = params.get("nh") || params.get("neighborhood") || "";
  if (!single) return [];
  const resolved = resolveSlugToken(single);
  return resolved ? [resolved] : [single.trim().toLowerCase()];
}

function normalizeSlugToken(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{M}/gu, "");
}

function resolveSlugToken(token) {
  if (!token || !marketOptions.length) return null;
  const norm = normalizeSlugToken(token);
  const bySlug = marketOptions.find((o) => o.slug === norm);
  if (bySlug) return bySlug.slug;
  const byName = marketOptions.find((o) => normalizeSlugToken(o.name) === norm);
  if (byName) return byName.slug;
  return null;
}

function getPickerCount(selected) {
  return Math.min(
    MAX_NEIGHBORHOODS,
    Math.max(DEFAULT_PICKERS, selected.length || MIN_NEIGHBORHOODS)
  );
}

function ensurePickers(count) {
  const wrap = document.getElementById("compare-pickers");
  if (!wrap) return [];
  const existing = [...wrap.querySelectorAll("select")];
  if (existing.length === count) return existing;

  wrap.innerHTML = "";
  const selects = [];
  for (let i = 0; i < count; i++) {
    const field = document.createElement("div");
    field.className = "compare-picker";

    const label = document.createElement("label");
    const labelText = document.createElement("span");
    labelText.className = "compare-picker-label";
    labelText.textContent = t("compare_nh_label", { n: i + 1 });

    const select = document.createElement("select");
    select.name = `nh-${i}`;
    select.required = i < MIN_NEIGHBORHOODS;
    select.disabled = !marketsReady;

    label.appendChild(labelText);
    label.appendChild(select);
    field.appendChild(label);
    wrap.appendChild(field);
    selects.push(select);
  }
  return selects;
}

function optionLabel(opt) {
  const parts = [opt.name];
  const total = (opt.rent_listings || 0) + (opt.sale_listings || 0);
  if (total > 0) parts.push(`(${total})`);
  return parts.join(" ");
}

function fillSelectOptions(select, selectedSlug) {
  const current = selectedSlug || select.value;
  select.innerHTML = "";
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = t("compare_nh_placeholder");
  select.appendChild(empty);

  for (const opt of marketOptions) {
    const o = document.createElement("option");
    o.value = opt.slug;
    o.textContent = optionLabel(opt);
    if (current && current === opt.slug) o.selected = true;
    select.appendChild(o);
  }

  if (current && !marketOptions.some((o) => o.slug === current)) {
    const missing = document.createElement("option");
    missing.value = current;
    missing.textContent = current;
    missing.selected = true;
    select.insertBefore(missing, select.firstChild?.nextSibling || null);
  }

  select.disabled = !marketsReady;
}

function renderPickers(selected = []) {
  const slugs = selected.length ? selected : selectedSlugs();
  const count = getPickerCount(slugs.length ? slugs : parseUrlSlugs());
  const selects = ensurePickers(count);
  selects.forEach((select, i) => {
    fillSelectOptions(select, slugs[i] || "");
  });
  updateFormState();
}

function selectedSlugs() {
  const form = document.getElementById("compare-form");
  if (!form) return [];
  const slugs = [];
  form.querySelectorAll("select").forEach((sel) => {
    const v = sel.value.trim();
    if (v && !slugs.includes(v)) slugs.push(v);
  });
  return slugs;
}

function setCompareEmptyVisible(visible) {
  const empty = document.getElementById("compare-empty");
  if (empty) empty.classList.toggle("hidden", !visible);
}

function setHint(text, { tone = "hint" } = {}) {
  const hint = document.getElementById("compare-hint");
  if (!hint) return;
  hint.textContent = text;
  hint.classList.remove("hint-error", "hint-ready");
  if (tone === "error") hint.classList.add("hint-error");
  if (tone === "ready") hint.classList.add("hint-ready");
}

function setSubmitState() {
  const btn = document.querySelector("#compare-form .btn-primary");
  if (!btn) return;
  btn.disabled = !marketsReady || compareLoading;
  btn.textContent = compareLoading ? t("compare_working") : t("compare_btn");
}

function updateFormState() {
  setSubmitState();
  const empty = document.getElementById("compare-empty");
  if (empty) {
    const skeletonOn = marketsLoading || compareLoading;
    empty.classList.toggle("is-skeleton-loading", skeletonOn);
    empty.setAttribute("aria-busy", skeletonOn ? "true" : "false");
  }
  if (!marketsReady) {
    setHint(marketsLoading ? t("compare_loading") : t("compare_markets_unavailable"), {
      tone: marketsLoading ? "hint" : "error",
    });
    return;
  }
  const slugs = selectedSlugs();
  if (slugs.length >= MIN_NEIGHBORHOODS) {
    setHint(t("compare_ready", { n: slugs.length }), { tone: "ready" });
  } else {
    setHint(t("compare_hint"), { tone: "hint" });
  }
}

function fmtSalePsm(v) {
  return v == null ? "—" : window.MetrikFormat.euroSalePsm(v);
}

function fmtRentPsm(v) {
  return v == null ? "—" : window.MetrikFormat.euroRentPsm(v);
}

function fmtRentMoney(v, suffix = "") {
  return v == null ? "—" : `${window.MetrikFormat.euroRent(v)}${suffix}`;
}

function fmtSaleMoney(v, suffix = "") {
  return v == null ? "—" : `${window.MetrikFormat.euroSale(v)}${suffix}`;
}

function confidenceBadge(level) {
  const safeLevel = window.MetrikSanitize.confidenceClass(level);
  const label = esc(window.MetrikI18n.translateConfidence(safeLevel));
  return `<span class="confidence-badge confidence-${safeLevel}">${label}</span>`;
}

function renderSummaryCards(neighborhoods) {
  const wrap = document.getElementById("compare-cards");
  if (!wrap) return;
  wrap.innerHTML = neighborhoods
    .map((n) => {
      const p = n.pulse;
      return `
        <article class="compare-nh-card">
          <div class="compare-nh-card-header">
            <a class="compare-nh-card-name" href="/market/neighborhood/${window.MetrikSanitize.pathSegment(n.slug)}">${esc(n.display_name)}</a>
            ${confidenceBadge(p.confidence)}
          </div>
          <dl class="compare-nh-stats">
            <div>
              <dt>${t("pulse_median_rent")}</dt>
              <dd>${esc(fmtRentMoney(p.median_rent_eur, t("per_month")))}</dd>
            </div>
            <div>
              <dt>${t("pulse_median_sale")}</dt>
              <dd>${esc(fmtSaleMoney(p.median_sale_eur))}</dd>
            </div>
            <div>
              <dt>${t("pulse_listings")}</dt>
              <dd>${esc(p.active_listings ?? "—")}</dd>
            </div>
          </dl>
          <p class="compare-nh-foot">${esc(t("pulse_meta", {
            n: p.observations ?? "—",
          }))}</p>
        </article>
      `;
    })
    .join("");
}

function groupRow(label, colCount) {
  return `<tr class="compare-group-row"><th colspan="${colCount + 1}">${esc(label)}</th></tr>`;
}

function metricRow(label, values, { format = (v) => v } = {}) {
  const cells = values.map((v) => `<td>${esc(format(v))}</td>`).join("");
  return `<tr class="compare-metric-row"><th scope="row">${esc(label)}</th>${cells}</tr>`;
}

function renderTable(data) {
  lastCompareData = data;
  const section = document.getElementById("compare-results");
  const body = document.getElementById("compare-body");
  const head = document.getElementById("compare-head-row");
  const error = document.getElementById("compare-error");
  if (!section || !body || !head) return;

  error?.classList.add("hidden");
  section.classList.remove("hidden");
  section.classList.add("content-fade-in");
  setCompareEmptyVisible(false);

  const cols = data.neighborhoods;
  const colCount = cols.length;
  renderSummaryCards(cols);

  head.innerHTML = `<th>${esc(t("compare_metric"))}</th>${cols
    .map((n) => `<th class="compare-col-head">${esc(n.display_name)}</th>`)
    .join("")}`;

  const pulses = cols.map((n) => n.pulse);
  body.innerHTML = [
    groupRow(t("compare_group_prices"), colCount),
    metricRow(t("pulse_sale_psm"), pulses.map((p) => p.average_sale_psm_eur), { format: fmtSalePsm }),
    metricRow(t("pulse_rent_psm"), pulses.map((p) => p.average_rent_psm_eur), { format: fmtRentPsm }),
    metricRow(t("pulse_median_sale"), pulses.map((p) => p.median_sale_eur), {
      format: (v) => fmtSaleMoney(v),
    }),
    metricRow(t("pulse_median_rent"), pulses.map((p) => p.median_rent_eur), {
      format: (v) => fmtRentMoney(v, t("per_month")),
    }),
    groupRow(t("compare_group_activity"), colCount),
    metricRow(t("pulse_listings"), pulses.map((p) => p.active_listings)),
    metricRow(t("pulse_median_dom"), pulses.map((p) => p.median_days_on_market), {
      format: (v) => (v == null ? "—" : t("listing_dom", { n: v })),
    }),
    groupRow(t("compare_group_profile"), colCount),
    metricRow(t("typical_apartment"), pulses.map((p) => p.typical_area_sqm), {
      format: (v) => (v == null ? "—" : window.MetrikFormat.area(v)),
    }),
    metricRow(t("bedrooms"), pulses.map((p) => p.typical_bedrooms), {
      format: (v) => (v == null ? "—" : t("bedrooms_count", { n: v })),
    }),
  ].join("");

  const fresh = document.getElementById("compare-freshness");
  if (fresh && data.corpus_updated_at) {
    fresh.hidden = false;
    fresh.textContent = t("data_updated_at", {
      date: window.MetrikFormat.dateTime(data.corpus_updated_at),
    });
  }

  setHint(t("compare_done", { n: cols.length }), { tone: "ready" });
  document.getElementById("compare-output-col")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function showError(msg) {
  const section = document.getElementById("compare-results");
  const error = document.getElementById("compare-error");
  const msgEl = document.getElementById("compare-error-msg");
  section?.classList.add("hidden");
  setCompareEmptyVisible(true);
  error?.classList.remove("hidden");
  if (msgEl) msgEl.textContent = msg;
  setHint(msg, { tone: "error" });
  error?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function parseApiError(payload) {
  if (!payload) return null;
  if (typeof payload.detail === "string") return payload.detail;
  if (Array.isArray(payload.detail)) {
    return payload.detail
      .map((item) => (typeof item === "string" ? item : item?.msg))
      .filter(Boolean)
      .join(" ");
  }
  return null;
}

async function loadCompare(slugs) {
  if (slugs.length < MIN_NEIGHBORHOODS) {
    showError(t("compare_need_two"));
    return;
  }
  const unique = [...new Set(slugs)];
  if (unique.length < slugs.length) {
    showError(t("compare_unique"));
    return;
  }
  if (!marketsReady) {
    showError(t("compare_loading"));
    return;
  }

  compareLoading = true;
  updateFormState();
  document.getElementById("compare-error")?.classList.add("hidden");

  try {
    const res = await fetch(
      `/api/compare?neighborhoods=${encodeURIComponent(unique.join(","))}`
    );
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) {
      showError(parseApiError(payload) || t("compare_failed"));
      return;
    }
    renderTable(payload);
    const url = new URL(window.location.href);
    url.searchParams.set("n", unique.join(","));
    window.history.replaceState({}, "", url);
    fetch("/api/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event: "compare_view", neighborhoods: unique }),
    }).catch(() => {});
  } catch {
    showError(t("compare_failed"));
  } finally {
    compareLoading = false;
    updateFormState();
  }
}

async function fetchMarkets(timeoutMs = 60000) {
  marketsLoading = true;
  updateFormState();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    let rows;
    if (window.MetrikApiCache) {
      rows = await window.MetrikApiCache.getJson("/api/markets", {
        ttlMs: 120_000,
        fetchInit: { signal: controller.signal },
      });
    } else {
      const res = await fetch("/api/markets", { signal: controller.signal });
      if (!res.ok) throw new Error("markets failed");
      rows = await res.json();
    }
    if (!Array.isArray(rows) || !rows.length) throw new Error("empty markets");
    marketOptions = rows
      .filter((row) => row?.slug && row?.name)
      .map((row) => ({
        slug: String(row.slug),
        name: String(row.name),
        rent_listings: Number(row.rent_listings || 0),
        sale_listings: Number(row.sale_listings || 0),
      }))
      .sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
    marketsReady = marketOptions.length > 0;
  } catch {
    marketsReady = false;
    marketOptions = [];
  } finally {
    clearTimeout(timer);
    marketsLoading = false;
    const preserved = selectedSlugs();
    const initial = parseUrlSlugs();
    renderPickers(preserved.length ? preserved : initial);
    updateFormState();
  }
}

function wireForm() {
  const form = document.getElementById("compare-form");
  form?.addEventListener("submit", (e) => {
    e.preventDefault();
    loadCompare(selectedSlugs());
  });

  document.getElementById("compare-pickers")?.addEventListener("change", () => {
    updateFormState();
  });
}

async function init() {
  const initial = parseUrlSlugs();
  renderPickers(initial);
  wireForm();
  await fetchMarkets();

  if (initial.length >= MIN_NEIGHBORHOODS && marketsReady) {
    await loadCompare(initial);
  }
}

document.addEventListener("metrik:langchange", () => {
  window.MetrikI18n.apply();
  const preserved = selectedSlugs();
  const initial = parseUrlSlugs();
  renderPickers(preserved.length ? preserved : initial);
  if (lastCompareData) renderTable(lastCompareData);
  else updateFormState();
});

init();
