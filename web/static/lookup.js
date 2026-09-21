const t = (k, v) => window.MetrikI18n.t(k, v);
const esc = (v) => window.MetrikSanitize.escapeHtml(v);

function propertyTypeLabel(ptype) {
  if (!ptype) return "";
  const key = `ptype_${ptype}`;
  const translated = t(key);
  return translated !== key ? translated : ptype;
}
const brand = () => window.MetrikI18n.t("brand");

function track(event, extra = {}) {
  if (window.MetrikTrack) {
    window.MetrikTrack.track(event, extra);
    return;
  }
  fetch("/api/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event, municipality: "Prishtina", ...extra }),
  }).catch(() => {});
}

function parsePath() {
  const parts = window.location.pathname.split("/").filter(Boolean);
  if (parts[0] !== "market" || parts.length < 3) return null;
  return { entity_type: parts[1], slug: parts[2] };
}

function fmtSalePsm(value) {
  return value == null ? "-" : window.MetrikFormat.euroSalePsm(value);
}

function fmtRentPsm(value) {
  // Public product no longer surfaces rent €/m²; keep helper for safe no-ops.
  if (value == null || value === 0) return "—";
  return window.MetrikFormat.euroRentPsm(value);
}

function fmtPsm(value) {
  return fmtSalePsm(value);
}

function fmtRentMoney(value, suffix = "") {
  if (value == null) return "-";
  return `${window.MetrikFormat.euroRent(value)}${suffix}`;
}

function fmtSaleMoney(value, suffix = "") {
  if (value == null) return "-";
  return window.MetrikFormat.euroSale(value);
}

let lastLookupData = null;
let lastHistoryData = null;
let marketLoadSeq = 0;
let marketVizSeq = 0;

function confTierLabel(level) {
  if (window.MetrikConfidence?.tierLabel) {
    return window.MetrikConfidence.tierLabel(level);
  }
  return window.MetrikI18n.translateConfidence(level);
}

document.addEventListener("metrik:langchange", () => {
  if (lastLookupData) {
    renderPriceTier(lastLookupData);
    renderRail(lastLookupData);
    setupValuateCta(lastLookupData);
    renderMarketVisuals(lastLookupData, lastHistoryData);
  }
});

function confidenceClass(level) {
  return `confidence-badge confidence-${level}`;
}

function marketPath(entityType, slug) {
  return `/market/${entityType}/${slug}`;
}

function safeHttpUrl(value) {
  try {
    const url = new URL(value, window.location.origin);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

function renderBreadcrumb(data) {
  const el = document.getElementById("breadcrumb");
  if (!el) return;
  el.replaceChildren();
  const appendSeparator = () => {
    const separator = document.createTextNode(" › ");
    el.appendChild(separator);
  };
  const home = document.createElement("a");
  home.href = "/";
  home.textContent = t("prishtina");
  el.appendChild(home);

  const chain = data.breadcrumb?.length ? data.breadcrumb : data.parent ? [data.parent] : [];
  for (const item of chain) {
    appendSeparator();
    const link = document.createElement("a");
    link.href = marketPath(item.entity_type || "neighborhood", item.slug);
    link.textContent = item.display_name;
    el.appendChild(link);
  }
  appendSeparator();
  const current = document.createElement("span");
  current.setAttribute("aria-current", "page");
  current.textContent = data.display_name;
  el.appendChild(current);
}

function renderChildren(data) {
  const section = document.getElementById("children-section");
  const list = document.getElementById("children-list");
  if (!section || !list) return;

  const children = data.children || [];
  if (!children.length) {
    section.classList.add("hidden");
    return;
  }

  section.classList.remove("hidden");
  list.innerHTML = "";
  for (const child of children) {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = marketPath(child.entity_type, child.slug);
    a.textContent = `${child.display_name} (${child.listings})`;
    li.appendChild(a);
    list.appendChild(li);
  }
}

function renderCanonicalNames(data) {
  const nameEl = document.getElementById("display-name");
  if (nameEl) nameEl.textContent = data.display_name;

  if (data.requested_slug && data.requested_slug !== data.slug) {
    const path = parsePath();
    if (path) {
      const canonical = marketPath(data.entity_type, data.slug);
      if (window.location.pathname !== canonical) {
        window.history.replaceState({}, "", canonical);
      }
    }
  }
}

function premiumPhrase(pct) {
  // Returns { text, dir } where dir ∈ "up"|"down"|"flat".
  if (pct == null) return { text: "", dir: "flat" };
  const dirWord =
    pct > 1 ? t("above_average") : pct < -1 ? t("below_average") : t("at_average");
  if (Math.abs(pct) <= 1) return { text: dirWord, dir: "flat" };
  const sign = pct > 0 ? "+" : "";
  return {
    text: `${sign}${Math.round(pct)}% ${dirWord}`,
    dir: pct > 0 ? "up" : "down",
  };
}

function renderPriceTier(data) {
  const el = document.getElementById("price-tier-badge");
  if (!el) return;
  const c = data.city_comparison;
  if (!c || !c.price_tier) {
    el.classList.add("hidden");
    return;
  }
  const { text } = premiumPhrase(c.premium_pct);
  el.textContent = text ? `${c.price_tier} · ${text}` : c.price_tier;
  el.className = `price-tier-badge tier-${c.price_tier.length}`;
  el.title = t("price_level");
  el.classList.remove("hidden");
}

function renderConfidencePanel(data) {
  const panel = document.getElementById("rail-confidence");
  if (!panel) return;
  const level = data.pulse.confidence;
  const badgeEl = document.getElementById("rail-confidence-badge");
  const bodyEl = document.getElementById("rail-confidence-body");
  if (!badgeEl || !bodyEl) return;
  badgeEl.textContent = confTierLabel(level);
  badgeEl.className = `confidence-badge confidence-${level}`;
  bodyEl.textContent = t(`conf_panel_body_${level}`, { n: data.pulse.active_listings });
  panel.hidden = false;
}

function renderPercentilePanel(data) {
  const panel = document.getElementById("rail-percentiles");
  if (!panel) return;
  const pc = data.price_percentiles;
  if (!pc || pc.p50_sale_psm == null) {
    panel.hidden = true;
    return;
  }
  document.getElementById("pct-p10").textContent = fmtSalePsm(pc.p10_sale_psm);
  document.getElementById("pct-p50").textContent = fmtSalePsm(pc.p50_sale_psm);
  document.getElementById("pct-p90").textContent = fmtSalePsm(pc.p90_sale_psm);
  renderPercentileRange(pc);
  const pctInfo = document.getElementById("pct-info");
  if (pctInfo) {
    pctInfo.setAttribute("data-i18n-tip", "percentile_info");
    pctInfo.setAttribute("data-i18n-tip-vars", JSON.stringify({ n: pc.n }));
    pctInfo.textContent = t("percentile_info", { n: pc.n });
    delete pctInfo.dataset.infoTipMounted;
    window.MetrikSite?.initInfoTips?.();
    const tip =
      document.getElementById("pct-info-tip") ||
      panel.querySelector(".rail-title .info-tip");
    if (tip) {
      tip.setAttribute("data-i18n-tip", "percentile_info");
      tip.setAttribute("data-i18n-tip-vars", JSON.stringify({ n: pc.n }));
      window.MetrikSite?.setInfoTipText?.(tip, t("percentile_info", { n: pc.n }));
    }
  }
  panel.hidden = false;
}

function renderPercentileRange(pc) {
  const range = document.getElementById("percentile-range");
  const fill = document.getElementById("pct-fill");
  const markP10 = document.getElementById("pct-mark-p10");
  const markP50 = document.getElementById("pct-mark-p50");
  const markP90 = document.getElementById("pct-mark-p90");
  if (!range || !fill || !markP10 || !markP50 || !markP90) return;

  const p10 = Number(pc.p10_sale_psm);
  const p50 = Number(pc.p50_sale_psm);
  const p90 = Number(pc.p90_sale_psm);
  if (![p10, p50, p90].every((n) => Number.isFinite(n)) || p90 <= p10) {
    range.hidden = true;
    range.setAttribute("aria-hidden", "true");
    return;
  }

  const span = p90 - p10;
  const medianPct = Math.min(100, Math.max(0, ((p50 - p10) / span) * 100));
  fill.style.left = "0%";
  fill.style.width = "100%";
  markP10.style.left = "0%";
  markP90.style.left = "100%";
  markP50.style.left = `${medianPct}%`;
  range.title = `${fmtSalePsm(p10)} → ${fmtSalePsm(p50)} → ${fmtSalePsm(p90)}`;
  range.hidden = false;
  range.setAttribute("aria-hidden", "false");
}

function renderCityPanel(data) {
  const panel = document.getElementById("rail-city");
  if (!panel) return;
  const c = data.city_comparison;
  if (!c) {
    panel.hidden = true;
    return;
  }
  const mo = t("per_month_suffix");
  document.getElementById("city-here-sale").textContent = fmtSalePsm(c.neighborhood_sale_psm);
  document.getElementById("city-city-sale").textContent = fmtSalePsm(c.city_median_sale_psm);
  document.getElementById("city-here-rent").textContent = fmtRentMoney(c.neighborhood_rent, mo);
  document.getElementById("city-city-rent").textContent = fmtRentMoney(c.city_median_rent, mo);
  const premEl = document.getElementById("city-premium");
  const { text, dir } = premiumPhrase(c.premium_pct);
  premEl.textContent = text;
  premEl.className = `city-premium${dir === "up" ? " premium-up" : dir === "down" ? " premium-down" : ""}`;
  panel.hidden = false;
}

function renderRail(data) {
  renderConfidencePanel(data);
  renderPercentilePanel(data);
  renderCityPanel(data);
}

function setupMarketActions(data) {
  const reportBtn = document.getElementById("market-report-btn");
  if (!reportBtn) return;

  reportBtn.hidden = false;
  reportBtn.onclick = () => {
    window.MetrikFeedback?.open({
      kind: "market",
      entity_type: data.entity_type,
      slug: data.slug,
      display_name: data.display_name,
    });
  };
}

function totalListings(data) {
  const stored = Number(data.total_listings);
  if (Number.isFinite(stored) && stored > 0) return stored;
  const active = Number(data.pulse?.active_listings);
  return Number.isFinite(active) && active > 0 ? active : 0;
}

const MIN_MARKET_LISTINGS = 10;

function renderPulse(data) {
  const p = data.pulse;
  const inventory = totalListings(data);
  lastLookupData = data;
  renderCanonicalNames(data);
  renderPriceTier(data);
  setupMarketActions(data);

  const lowNote = document.getElementById("low-confidence-note");
  if (p.confidence === "low" || p.confidence === "medium") {
    lowNote.classList.remove("hidden");
    lowNote.textContent =
      p.confidence === "low" ? t("limited_data") : t("moderate_data");
  } else {
    lowNote.classList.add("hidden");
  }

  const disclaimer = document.getElementById("market-analysis-disclaimer");
  const disclaimerBadge = document.getElementById("market-analysis-disclaimer-badge");
  const disclaimerText = document.getElementById("market-analysis-disclaimer-text");
  const showAnalysisDisclaimer =
    p.confidence === "insufficient" && inventory >= MIN_MARKET_LISTINGS;
  if (disclaimer) {
    disclaimer.classList.toggle("hidden", !showAnalysisDisclaimer);
    if (showAnalysisDisclaimer) {
      if (disclaimerBadge) {
        disclaimerBadge.textContent = t("conf_tier_insufficient");
      }
      if (disclaimerText) {
        disclaimerText.textContent = t("market_analysis_disclaimer", {
          total: inventory,
        });
      }
    }
  }

  // Sale €/m², median sale, monthly rent, inventory — no public rent €/m².
  document.getElementById("pulse-sale-psm").textContent = fmtSalePsm(p.average_sale_psm_eur);
  document.getElementById("pulse-median-sale").textContent = fmtSaleMoney(p.median_sale_eur);
  document.getElementById("pulse-median-rent").textContent = fmtRentMoney(
    p.median_rent_eur,
    t("per_month_suffix")
  );
  document.getElementById("pulse-inventory").textContent = String(inventory);
  renderRail(data);

  const typicalSection = document.getElementById("typical-section");
  const hasTypical = p.typical_area_sqm || p.typical_bedrooms != null || p.median_sale_eur;
  if (typicalSection) {
    if (!hasTypical) {
      typicalSection.classList.add("hidden");
    } else {
      typicalSection.classList.remove("hidden");
      document.getElementById("typical-area").textContent = p.typical_area_sqm
        ? window.MetrikFormat.area(p.typical_area_sqm)
        : "-";
      document.getElementById("typical-beds").textContent =
        p.typical_bedrooms != null ? t("bedrooms_count", { n: p.typical_bedrooms }) : "-";
      document.getElementById("typical-price").textContent = fmtSaleMoney(p.median_sale_eur);
    }
  }
}

function renderInsufficient(data) {
  const p = data.pulse;
  const inventory = totalListings(data);
  document.getElementById("market-title").textContent = data.display_name;
  renderCanonicalNames(data);
  const badge = document.getElementById("insufficient-badge");
  if (badge) badge.textContent = window.MetrikI18n.translateConfidence("insufficient");
  document.getElementById("insufficient-msg").textContent = t("insufficient_msg");
  document.getElementById("insufficient-detail").textContent =
    `${inventory} ${t("listings")} · ${t("insufficient_detail")}. ${t("insufficient_need")}`;

  const parentLink = document.getElementById("insufficient-parent-link");
  if (data.parent) {
    parentLink.href = marketPath("neighborhood", data.parent.slug);
    parentLink.textContent = `View ${data.parent.display_name}`;
    parentLink.classList.remove("hidden");
  } else if (data.entity_type === "neighborhood") {
    parentLink.classList.add("hidden");
  } else {
    parentLink.classList.add("hidden");
  }

  renderRecentList(data.recent_listings, "insufficient-recent", "insufficient-recent-wrap");
  setupInsufficientValuate(data);
}

function setupInsufficientValuate(data) {
  const nhName =
    data.entity_type === "neighborhood"
      ? data.display_name
      : data.parent?.display_name || data.display_name;
  document.getElementById("insufficient-valuate-nh").value = nhName;
  const nhDisplay = document.getElementById("insufficient-valuate-nh-display");
  if (nhDisplay) nhDisplay.value = nhName;

  document.getElementById("insufficient-valuate-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const body = {
      neighborhood: nhName,
      area_sqm: Number(document.getElementById("insufficient-valuate-area").value),
    };
    const beds = document.getElementById("insufficient-valuate-beds").value;
    if (beds) body.bedrooms = Number(beds);

    const out = document.getElementById("insufficient-valuate-result");
    track("valuation_search", {
      neighborhood: body.neighborhood,
      area_sqm: body.area_sqm,
      bedrooms: body.bedrooms ?? null,
      entity_type: data.entity_type,
      slug: data.slug,
      section: "insufficient_market",
    });

    try {
      const res = await fetch("/api/valuate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = await res.json();
      out.textContent = res.ok
        ? t("fair_rent_estimate", {
            price: window.MetrikFormat.int(window.MetrikFormat.roundRent(payload.point_estimate_eur)),
            confidence: payload.confidence_label,
          })
        : payload.detail || t("valuation_failed");
      out.classList.remove("hidden");
    } catch {
      out.textContent = t("valuation_unavailable");
      out.classList.remove("hidden");
    }
  });
}

function renderSaleByPropertyType(rows) {
  const section = document.getElementById("sale-type-section");
  const tbody = document.querySelector("#sale-type-table tbody");
  if (!section || !tbody) return;

  const visible = (rows || []).filter((r) => r.listings >= 3);
  if (!visible.length) {
    section.classList.add("hidden");
    return;
  }

  section.classList.remove("hidden");
  tbody.innerHTML = "";
  for (const row of visible) {
    const tr = document.createElement("tr");
    tr.className = window.MetrikConfidence.rowClass({ confidence: row.confidence, n: row.listings });
    tr.innerHTML = `
      <td>${esc(row.label)}</td>
      <td>${esc(fmtSalePsm(row.average_sale_psm_eur))}</td>
      <td>${esc(fmtSaleMoney(row.median_sale_eur))}</td>
      <td>${row.median_area_sqm != null ? esc(window.MetrikFormat.area(row.median_area_sqm)) : "-"}</td>
      <td>${esc(row.listings)}</td>
      <td>${window.MetrikConfidence.badge({ confidence: row.confidence }, { levelOnly: true })}</td>
    `;
    tbody.appendChild(tr);
  }
}

function fillTable(tableId, rows, labelKey) {
  const tbody = document.querySelector(`#${tableId} tbody`);
  if (!tbody) return;
  tbody.innerHTML = "";
  const visible = (rows || []).filter((r) => r.listings >= 5);
  const section = document.getElementById(tableId.replace("-table", "-section"));
  if (!section) return;
  if (!visible.length) {
    section.classList.add("hidden");
    return;
  }
  section.classList.remove("hidden");
  for (const row of visible) {
    const tr = document.createElement("tr");
    tr.className = window.MetrikConfidence.rowClass({ confidence: row.confidence, n: row.listings });
    tr.innerHTML = `
      <td>${esc(row[labelKey])}</td>
      <td>${esc(fmtSalePsm(row.average_sale_psm_eur))}</td>
      <td>${esc(fmtRentMoney(row.median_rent_eur, t("per_month_suffix")))}</td>
      <td>${esc(row.listings)}</td>
      <td>${window.MetrikConfidence.badge({ confidence: row.confidence }, { levelOnly: true })}</td>
    `;
    tbody.appendChild(tr);
  }
}

const RECENT_LISTINGS_INITIAL = 4;

function formatRecentListing(item) {
  const br =
    item.bedrooms != null
      ? t("recent_bedrooms", { n: item.bedrooms })
      : t("recent_bedrooms_unknown");
  const area =
    item.area_sqm != null
      ? t("recent_area", { n: item.area_sqm })
      : t("recent_area_unknown");
  const price =
    item.listing_type === "rent"
      ? fmtRentMoney(item.price_eur, t("per_month"))
      : fmtSaleMoney(item.price_eur);
  const typeLabel = item.listing_type === "rent" ? t("listing_rent") : t("listing_sale");
  return `${typeLabel} · ${area} · ${br} · ${price}`;
}

function renderRecentList(listings, listId, wrapId, { expandable = false } = {}) {
  const ul = document.getElementById(listId);
  const wrap = wrapId ? document.getElementById(wrapId) : null;
  const section = expandable ? document.getElementById("recent-listings-section") : null;
  const curtain = expandable ? document.getElementById("recent-listings-curtain") : null;
  if (!ul) return;

  ul.innerHTML = "";
  curtain?.querySelector(".recent-list-reveal")?.remove();
  curtain?.classList.remove("is-expanded", "has-more");

  if (!listings?.length) {
    if (wrap) wrap.classList.add("hidden");
    section?.classList.add("hidden");
    return;
  }
  if (wrap) wrap.classList.remove("hidden");
  section?.classList.remove("hidden");

  listings.forEach((item, index) => {
    const li = document.createElement("li");
    li.classList.add("recent-listing-item");
    if (expandable && index >= RECENT_LISTINGS_INITIAL) {
      li.classList.add("recent-listing-extra");
    }
    const a = document.createElement("a");
    a.classList.add("recent-listing-link");
    a.textContent = formatRecentListing(item);
    const safeUrl = safeHttpUrl(item.url);
    if (safeUrl) {
      a.href = safeUrl;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
    } else {
      a.removeAttribute("href");
      a.setAttribute("aria-disabled", "true");
    }
    li.appendChild(a);
    ul.appendChild(li);
  });

  if (!expandable || listings.length <= RECENT_LISTINGS_INITIAL || !section || !curtain) {
    return;
  }

  curtain.classList.add("has-more");
  const reveal = document.createElement("div");
  reveal.className = "recent-list-reveal";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "recent-list-toggle";
  btn.textContent = t("show_all_listings", { n: listings.length });
  btn.addEventListener("click", () => {
    const expanded = curtain.classList.toggle("is-expanded");
    btn.textContent = expanded
      ? t("show_less_listings")
      : t("show_all_listings", { n: listings.length });
  });
  reveal.appendChild(btn);
  curtain.appendChild(reveal);
}

function renderRecent(listings) {
  renderRecentList(listings, "recent-listings", null, { expandable: true });
}

function formatHistoryLabel(periodEnd) {
  if (!periodEnd) return "";
  try {
    return window.MetrikFormat?.dateShort?.(periodEnd) || String(periodEnd).slice(0, 10);
  } catch {
    return String(periodEnd).slice(0, 10);
  }
}

function confLabel(level) {
  if (!level) return "";
  return confTierLabel(level);
}

function avgSample(points, key) {
  const vals = (points || []).map((p) => Number(p[key]) || 0).filter((n) => n > 0);
  if (!vals.length) return 0;
  return Math.round(vals.reduce((a, b) => a + b, 0) / vals.length);
}

function clearSparklines() {
  for (const id of ["spark-sale-psm", "spark-median-rent", "spark-inventory"]) {
    const canvas = document.getElementById(id);
    if (!canvas) continue;
    window.MetrikCharts?.destroy?.(canvas);
    canvas.hidden = true;
    canvas.closest(".pulse-spark-wrap")?.setAttribute("hidden", "");
  }
}

async function renderSparklines(history) {
  const charts = window.MetrikCharts;
  if (!charts) {
    clearSparklines();
    return;
  }
  await charts.ensureChartJs();
  const points = history?.points || [];
  const theme = charts.theme();

  const specs = [
    { id: "spark-sale-psm", key: "median_sale_psm_eur", color: theme.primary },
    { id: "spark-median-rent", key: "median_rent_eur", color: theme.tertiary },
    { id: "spark-inventory", key: "inventory_n", color: theme.secondary },
  ];

  for (const spec of specs) {
    const canvas = document.getElementById(spec.id);
    const wrap = canvas?.closest(".pulse-spark-wrap");
    if (!canvas || !wrap) continue;
    const values = points.map((p) => p[spec.key]);
    const chart = charts.createSparkline(canvas, { values, color: spec.color });
    if (chart) {
      wrap.hidden = false;
      wrap.removeAttribute("hidden");
    } else {
      wrap.hidden = true;
      wrap.setAttribute("hidden", "");
    }
  }
}

async function renderHistoryCharts(history) {
  const section = document.getElementById("market-history-section");
  const empty = document.getElementById("market-history-empty");
  const chartsWrap = document.getElementById("market-history-charts");
  const charts = window.MetrikCharts;
  if (!section || !charts) return;

  const points = history?.points || [];
  const salePoints = points.filter((p) => p.median_sale_psm_eur != null);
  const rentPoints = points.filter((p) => p.median_rent_eur != null);
  const usable = salePoints.length >= 3 || rentPoints.length >= 3;

  if (!usable) {
    section.classList.remove("hidden");
    if (chartsWrap) {
      chartsWrap.hidden = true;
      chartsWrap.classList.add("hidden");
    }
    if (empty) {
      empty.hidden = false;
      empty.textContent = t("market_history_insufficient");
    }
    charts.destroy(document.getElementById("historySaleChart"));
    charts.destroy(document.getElementById("historyRentChart"));
    return;
  }

  section.classList.remove("hidden");
  if (chartsWrap) {
    chartsWrap.hidden = false;
    chartsWrap.classList.remove("hidden");
  }
  if (empty) empty.hidden = true;

  await charts.ensureChartJs();
  const theme = charts.theme();
  const labels = points.map((p) => formatHistoryLabel(p.period_end || p.period_start));

  const saleCanvas = document.getElementById("historySaleChart");
  const rentCanvas = document.getElementById("historyRentChart");
  const saleNote = document.getElementById("history-sale-note");
  const rentNote = document.getElementById("history-rent-note");

  if (saleCanvas && salePoints.length >= 3) {
    charts.createLineChart(saleCanvas, {
      labels,
      beginAtZero: false,
      datasets: [
        {
          label: t("market_history_sale"),
          data: points.map((p) => p.median_sale_psm_eur),
          borderColor: theme.primary,
          backgroundColor: theme.primaryFill,
          fill: true,
        },
      ],
      tooltipBuilder: (items) => {
        const idx = items[0]?.dataIndex ?? 0;
        const p = points[idx];
        if (!p) return { title: "", lines: [] };
        return {
          title: formatHistoryLabel(p.period_end || p.period_start),
          lines: [
            `${t("market_history_sale")}: ${fmtSalePsm(p.median_sale_psm_eur)}`,
            t("chart_tooltip_n", { n: p.sale_n ?? 0 }),
            t("chart_tooltip_confidence", { level: confLabel(p.sale_confidence) }),
          ],
        };
      },
    });
    charts.setNote(saleNote, t("market_history_sale_note", { n: avgSample(points, "sale_n") || "—" }));
  } else {
    charts.destroy(saleCanvas);
    charts.setNote(saleNote, t("market_history_insufficient"));
  }

  if (rentCanvas && rentPoints.length >= 3) {
    charts.createLineChart(rentCanvas, {
      labels,
      beginAtZero: false,
      datasets: [
        {
          label: t("market_history_rent"),
          data: points.map((p) => p.median_rent_eur),
          borderColor: theme.tertiary,
          backgroundColor: theme.tertiaryFill,
          fill: true,
        },
      ],
      tooltipBuilder: (items) => {
        const idx = items[0]?.dataIndex ?? 0;
        const p = points[idx];
        if (!p) return { title: "", lines: [] };
        return {
          title: formatHistoryLabel(p.period_end || p.period_start),
          lines: [
            `${t("market_history_rent")}: ${fmtRentMoney(p.median_rent_eur, t("per_month_suffix"))}`,
            t("chart_tooltip_n", { n: p.rent_n ?? 0 }),
            t("chart_tooltip_confidence", { level: confLabel(p.rent_confidence) }),
          ],
        };
      },
    });
    charts.setNote(rentNote, t("market_history_rent_note", { n: avgSample(points, "rent_n") || "—" }));
  } else {
    charts.destroy(rentCanvas);
    charts.setNote(rentNote, t("market_history_insufficient"));
  }
}

function formatBinLabel(bin) {
  const start = bin.bin_start;
  const end = bin.bin_end;
  if (start == null || end == null) return "—";
  return `${start}–${end}`;
}

async function renderDistributionCharts(data) {
  const section = document.getElementById("market-distribution-section");
  const charts = window.MetrikCharts;
  if (!section || !charts) return;

  const saleDist = data.sale_price_distribution;
  const rentDist = data.rent_price_distribution;
  const saleOk = (saleDist?.bins || []).length >= 2 && (saleDist?.n || 0) >= 10;
  const rentOk = (rentDist?.bins || []).length >= 2 && (rentDist?.n || 0) >= 10;

  if (!saleOk && !rentOk) {
    section.classList.add("hidden");
    charts.destroy(document.getElementById("distSaleChart"));
    charts.destroy(document.getElementById("distRentChart"));
    return;
  }

  section.classList.remove("hidden");
  await charts.ensureChartJs();
  const theme = charts.theme();
  const medianLabel = t("market_distribution_median_line");

  async function paint(kind, dist, canvasId, wrapId, noteId, median, color) {
    const canvas = document.getElementById(canvasId);
    const wrap = document.getElementById(wrapId);
    const note = document.getElementById(noteId);
    const panel = document.getElementById(kind === "sale" ? "dist-sale-panel" : "dist-rent-panel");
    const ok = (dist?.bins || []).length >= 2 && (dist?.n || 0) >= 10;
    if (!ok) {
      if (panel) panel.hidden = true;
      charts.destroy(canvas);
      return;
    }
    if (panel) panel.hidden = false;
    charts.showChart(wrap);
    const bins = dist.bins;
    const labels = bins.map(formatBinLabel);
    const values = bins.map((b) => b.count || 0);
    const centers = bins.map((b) => (Number(b.bin_start) + Number(b.bin_end)) / 2);
    charts.createHistogram(canvas, {
      labels,
      values,
      binCenters: centers,
      median: median != null ? Number(median) : null,
      medianLabel,
      color,
      tooltipBuilder: (items) => {
        const idx = items[0]?.dataIndex ?? 0;
        const bin = bins[idx];
        if (!bin) return { title: "", lines: [] };
        return {
          title: `${formatBinLabel(bin)} ${kind === "sale" ? t("market_distribution_psm") : t("market_distribution_rent_unit")}`,
          lines: [
            t("market_distribution_count", { n: bin.count || 0 }),
            t("chart_tooltip_sample", { n: dist.n || 0, confidence: confLabel(dist.confidence) }),
          ],
        };
      },
    });
    charts.setNote(
      note,
      t("market_distribution_note", {
        n: dist.n || 0,
        confidence: confLabel(dist.confidence),
      })
    );
  }

  await paint(
    "sale",
    saleDist,
    "distSaleChart",
    "dist-sale-wrap",
    "dist-sale-note",
    data.pulse?.average_sale_psm_eur ?? data.price_percentiles?.p50_sale_psm,
    theme.primary
  );
  await paint(
    "rent",
    rentDist,
    "distRentChart",
    "dist-rent-wrap",
    "dist-rent-note",
    data.pulse?.median_rent_eur,
    theme.tertiary
  );
}

async function renderMarketVisuals(data, history) {
  const seq = ++marketVizSeq;
  try {
    await Promise.all([
      renderHistoryCharts(history),
      renderDistributionCharts(data),
      renderSparklines(history),
    ]);
  } catch (err) {
    console.error("market visuals failed", err);
  }
  if (seq !== marketVizSeq) return;
}

async function fetchMarketHistory(entityType, slug) {
  try {
    const url = `/api/lookup/${entityType}/${slug}/history?months=12`;
    const res = await fetchWithTimeout(url, 12000);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

function setupValuateCta(data, onInsufficient = false) {
  const btn = document.getElementById("valuate-cta-btn");
  if (!btn) return;

  const nhName =
    data.entity_type === "neighborhood"
      ? data.display_name
      : data.parent?.display_name || data.display_name;

  const params = new URLSearchParams();
  if (nhName) params.set("neighborhood", nhName);
  if (!onInsufficient) {
    if (data.pulse.typical_area_sqm) {
      params.set("area", String(Math.round(data.pulse.typical_area_sqm)));
    }
    if (data.pulse.typical_bedrooms != null) {
      params.set("bedrooms", String(data.pulse.typical_bedrooms));
    }
  }

  const query = params.toString();
  btn.href = query ? `/valuate?${query}` : "/valuate";

  const lead = document.getElementById("valuate-cta-lead");
  if (lead) lead.textContent = t("valuate_cta_lead", { nh: nhName || t("prishtina") });

  btn.onclick = () => {
    track("valuation_cta_click", {
      neighborhood: nhName,
      entity_type: data.entity_type,
      slug: data.slug,
    });
  };
}

function setupHeaderSearch() {
  window.MetrikSearch?.init({
    input: document.getElementById("header-search"),
    list: document.getElementById("header-search-results"),
    root: document.getElementById("header-search-wrap")?.closest(".market-toolbar"),
    minChars: 1,
    section: "market",
  });
}

function fetchWithTimeout(url, ms = 30000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  return fetch(url, { signal: controller.signal }).finally(() => clearTimeout(timer));
}

function renderMarketData(data, history = null) {
  renderBreadcrumb(data);

  const inventory = totalListings(data);
  const showInsufficient =
    data.pulse.confidence === "insufficient" && inventory < MIN_MARKET_LISTINGS;

  if (showInsufficient) {
    document.getElementById("market-content")?.classList.add("hidden");
    document.getElementById("insufficient")?.classList.remove("hidden");
    document.getElementById("market-history-section")?.classList.add("hidden");
    document.getElementById("market-distribution-section")?.classList.add("hidden");
    clearSparklines();
    renderInsufficient(data);
    setupMarketActions(data);
    return;
  }

  document.getElementById("insufficient")?.classList.add("hidden");
  document.getElementById("market-content")?.classList.remove("hidden");
  document.getElementById("market-content")?.classList.add("content-fade-in");
  renderPulse(data);
  renderChildren(data);
  renderSaleByPropertyType(data.sale_by_property_type);
  fillTable("bedroom-table", data.bedroom_breakdown, "label");
  fillTable("size-table", data.size_breakdown, "label");
  renderRecent(data.recent_listings);
  setupValuateCta(data);
  lastHistoryData = history;
  renderMarketVisuals(data, history);
}

async function loadMarket() {
  const seq = ++marketLoadSeq;
  const path = parsePath();
  if (!path) {
    document.getElementById("not-found").classList.remove("hidden");
    document.getElementById("loading").classList.add("hidden");
    return;
  }

  const loadingEl = document.getElementById("loading");
  const loadingHint = loadingEl?.querySelector(".hint");
  document.getElementById("load-error")?.classList.add("hidden");
  document.getElementById("not-found")?.classList.add("hidden");
  loadingEl?.classList.remove("hidden");

  const slowTimer = setTimeout(() => {
    if (seq !== marketLoadSeq) return;
    if (loadingHint && !loadingEl.classList.contains("hidden")) {
      loadingHint.textContent = t("market_loading_slow");
    }
  }, 8000);

  try {
    const res = await fetchWithTimeout(`/api/lookup/${path.entity_type}/${path.slug}`);
    if (seq !== marketLoadSeq) return;

    loadingEl.classList.add("hidden");
    if (res.status === 404) {
      document.getElementById("not-found").classList.remove("hidden");
      return;
    }
    if (!res.ok) throw new Error("lookup failed");

    const data = await res.json();
    if (seq !== marketLoadSeq) return;

    document.getElementById("load-error")?.classList.add("hidden");

    track("market_page_viewed", {
      entity_type: data.entity_type,
      slug: data.slug,
      neighborhood: data.display_name,
      municipality: data.city || "Prishtina",
      confidence: data.pulse.confidence,
      confidence_tier: data.pulse.confidence,
    });

    // Render snapshot immediately; history is optional and may hit a colder path.
    renderMarketData(data, null);
    document.title = `${data.display_name}, ${brand()}`;

    const history = await fetchMarketHistory(data.entity_type, data.slug);
    if (seq !== marketLoadSeq) return;
    lastHistoryData = history;
    if (history) {
      await renderMarketVisuals(data, history);
    }
  } catch (err) {
    if (seq !== marketLoadSeq) return;

    loadingEl.classList.add("hidden");
    const errPanel = document.getElementById("load-error");
    if (errPanel) {
      errPanel.classList.remove("hidden");
      const msg = errPanel.querySelector(".hint");
      if (msg) msg.textContent = t("market_load_error");
    } else {
      document.getElementById("not-found").classList.remove("hidden");
    }
  } finally {
    clearTimeout(slowTimer);
  }
}

setupHeaderSearch();
document.getElementById("market-retry")?.addEventListener("click", () => {
  loadMarket();
});
loadMarket();
