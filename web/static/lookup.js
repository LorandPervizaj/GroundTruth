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
let marketLoadSeq = 0;

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
  const pctHint = document.getElementById("pct-hint");
  if (pctHint) {
    pctHint.classList.add("hint-info");
    pctHint.setAttribute("data-i18n-tip", "percentile_hint");
    pctHint.setAttribute("data-i18n-tip-vars", JSON.stringify({ n: pc.n }));
    pctHint.textContent = t("percentile_hint", { n: pc.n });
    delete pctHint.dataset.infoTipMounted;
    window.MetrikSite?.initInfoTips?.();
    const tip =
      document.getElementById("pct-hint-tip") ||
      panel.querySelector(".rail-title .info-tip");
    if (tip) {
      tip.setAttribute("data-i18n-tip", "percentile_hint");
      tip.setAttribute("data-i18n-tip-vars", JSON.stringify({ n: pc.n }));
      window.MetrikSite?.setInfoTipText?.(tip, t("percentile_hint", { n: pc.n }));
    }
  }
  panel.hidden = false;
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

  // Card 1: sale €/m². Card 2: rent €/m²/mo. Card 3: median sale. Card 4: median monthly rent.
  document.getElementById("pulse-sale-psm").textContent = fmtSalePsm(p.average_sale_psm_eur);
  document.getElementById("pulse-rent-psm").textContent =
    p.average_rent_psm_eur == null
      ? "-"
      : `${fmtRentPsm(p.average_rent_psm_eur)}${t("per_month_suffix")}`;
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
      <td>${esc(fmtRentPsm(row.average_rent_psm_eur))}</td>
      <td>${esc(fmtRentMoney(row.median_rent_eur, "/mo"))}</td>
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

function renderMarketData(data) {
  renderBreadcrumb(data);

  const inventory = totalListings(data);
  const showInsufficient =
    data.pulse.confidence === "insufficient" && inventory < MIN_MARKET_LISTINGS;

  if (showInsufficient) {
    document.getElementById("market-content")?.classList.add("hidden");
    document.getElementById("insufficient")?.classList.remove("hidden");
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

    renderMarketData(data);

    if (seq !== marketLoadSeq) return;
    document.title = `${data.display_name}, ${brand()}`;
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
