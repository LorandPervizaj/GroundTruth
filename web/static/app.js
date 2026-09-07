let lastSearch = {};
let lastValuationResult = null;
let neighborhoodData = [];
let valuationMode = "rent";

const t = (k, vars) => window.MetrikI18n.t(k, vars);
const esc = (v) => window.MetrikSanitize.escapeHtml(v);
const money = (n, isRent = true) =>
  window.MetrikFormat.int(
    isRent ? window.MetrikFormat.roundRent(n) : window.MetrikFormat.roundSale(n)
  );

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function tf(k, fallback) {
  const translated = t(k);
  return translated === k ? fallback : translated;
}

function isEnglish() {
  return window.MetrikI18n.getLang() === "en";
}

function translateConfidenceLabel(label) {
  return window.MetrikI18n.translateConfidence(String(label || "").toLowerCase());
}

function translateWhyCheck(line) {
  if (!line || isEnglish()) return line;
  const nComps = line.match(/^(\d+) comparable apartments$/);
  if (nComps) return t("why_n_comparables", { n: nComps[1] });
  if (line === "Same neighborhood") return t("why_same_nh");
  const size = line.match(/^Similar size \(~(\d+) m², ±(\d+) m²\)$/);
  if (size) return t("why_similar_size", { center: size[1], tol: size[2] });
  if (line === "Closer in size weighted more heavily") return t("why_size_weighted");
  if (line === "Similar bedrooms") return t("why_similar_beds");
  if (line === "Bedrooms not matched (insufficient stratified sample)") return t("why_beds_unmatched");
  return line;
}

function translateMethodSummary(text) {
  if (!text || isEnglish()) return text;
  const withBeds = text.includes("with bedroom-matched comparables");
  let out = t("method_summary_base");
  if (withBeds) out += t("method_summary_beds");
  if (text.includes("furnishing effect not applied")) out += t("method_summary_furnishing");
  return out;
}

function translateFactor(text) {
  if (!text || isEnglish()) return text;
  const map = {
    "Area-weighted €/m²": t("factor_area_weighted"),
    "Neighborhood comparables": t("factor_nh_comps"),
    "Bedroom-matched comparables": t("factor_bed_matched"),
  };
  return map[text] || text;
}

function translateExcluded(text) {
  if (!text || isEnglish()) return text;
  const map = {
    "furnishing (GT-006)": t("excluded_furnishing"),
    floor: t("excluded_floor"),
    parking: t("excluded_parking"),
  };
  return map[text] || text;
}

function translateConfidenceNote(text) {
  if (!text || isEnglish()) return text;
  if (text.startsWith("Comparables drawn from") || text.startsWith("Single-source dataset")) {
    return t("note_single_source");
  }
  if (text.startsWith("Commercial/office listings excluded")) return t("note_commercial_excluded");
  if (text === "Small comparable sample, treat range as indicative.") return t("note_small_sample");
  const sample = text.match(/^Comparable sample n=(\d+) \((.+)\)\.$/);
  if (sample) return t("note_sample_n", { n: sample[1], method: sample[2] });
  return text;
}

function modeCopyFor(kind) {
  return MODE_COPY[kind === "sale" ? "sale" : "rent"];
}

function isRentResult(data) {
  return (data?.valuation_type || valuationMode) !== "sale";
}

function setSuffixVisibility(isRent) {
  const suffix = isRent ? t("per_month_suffix") : "";
  document.querySelectorAll(".val-suffix").forEach((el) => {
    el.textContent = suffix;
    el.classList.toggle("hidden", !isRent);
  });
}

function fmtAskingValue(value) {
  if (value == null || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return "—";
  if (valuationMode === "rent") {
    return `${window.MetrikFormat.euroRent(n)}${t("per_month_suffix")}`;
  }
  return window.MetrikFormat.euroSale(n);
}

function syncAreaSlider(value) {
  const slider = document.getElementById("area-slider");
  const hidden = document.getElementById("area");
  const out = document.getElementById("area-slider-out");
  const next = Math.min(200, Math.max(20, Number(value) || 78));
  if (slider) slider.value = String(next);
  if (hidden) hidden.value = String(next);
  if (out) out.textContent = `${next} m²`;
}

function syncAskingSlider({ setValue = false, value = null } = {}) {
  const c = modeCopy();
  const slider = document.getElementById("asking-slider");
  const hidden = document.getElementById("asking-price");
  const out = document.getElementById("asking-slider-out");
  if (!slider || !hidden) return;

  slider.min = String(c.askingMin);
  slider.max = String(c.askingMax);
  slider.step = String(c.askingStep);

  if (setValue) {
    const n = Number(value);
    if (Number.isFinite(n) && n > 0) {
      const clamped = Math.min(c.askingMax, Math.max(c.askingMin, n));
      slider.value = String(clamped);
      hidden.value = String(clamped);
    } else {
      hidden.value = "";
      slider.value = String(Number(c.askingPlaceholder) || c.askingMin);
    }
  } else if (hidden.value) {
    // keep current asking if still in range; otherwise clear
    const cur = Number(hidden.value);
    if (!Number.isFinite(cur) || cur < c.askingMin || cur > c.askingMax) {
      hidden.value = "";
      slider.value = String(Number(c.askingPlaceholder) || c.askingMin);
    } else {
      slider.value = String(cur);
    }
  } else {
    slider.value = String(Number(c.askingPlaceholder) || c.askingMin);
  }

  if (out) out.textContent = fmtAskingValue(hidden.value);
}

function clearAskingPrice() {
  const hidden = document.getElementById("asking-price");
  if (hidden) hidden.value = "";
  syncAskingSlider();
  updatePropertySummaryPreview();
  updateEmptyPreview();
}

function wireValuateSliders() {
  const areaSlider = document.getElementById("area-slider");
  areaSlider?.addEventListener("input", () => {
    syncAreaSlider(areaSlider.value);
    updatePropertySummaryPreview();
    updateEmptyPreview();
  });

  const askingSlider = document.getElementById("asking-slider");
  askingSlider?.addEventListener("input", () => {
    syncAskingSlider({ setValue: true, value: askingSlider.value });
    updatePropertySummaryPreview();
    updateEmptyPreview();
  });

  document.getElementById("asking-clear")?.addEventListener("click", clearAskingPrice);
}

function renderEstimateValue(amount, isRent) {
  const el = document.getElementById("estimate-value");
  if (!el) return;
  el.textContent = formatValuationEuro(amount, isRent);
}

function resetValuationOutput() {
  const el = document.getElementById("estimate-value");
  if (el) el.textContent = "—";
  const rangeLine = document.getElementById("range-line");
  if (rangeLine) rangeLine.textContent = "";
  const basedOn = document.getElementById("based-on-line");
  if (basedOn) basedOn.textContent = "";
  const confidenceBadge = document.getElementById("confidence-badge");
  if (confidenceBadge) confidenceBadge.textContent = "";
  const preview = document.getElementById("property-summary");
  if (preview) {
    preview.innerHTML = "";
    preview.hidden = true;
  }
}

function updateResultLabels(kind) {
  const c = modeCopyFor(kind);
  setText("fair-estimate-label", t(c.fairEstimateKey));
  setText("compare-fair-label", t(c.fairEstimateKey));
  setText("compare-asking-label", t(c.askingLabelKey));
  setText("comparables-summary-label", t(c.comparablesKey));
}

function translateAssessmentShort(data, isRent) {
  const pct = Math.abs(Math.round(data.vs_median_pct ?? 0));
  const base = isRent ? "valuate_assessment" : "valuate_sale_assessment";
  if (data.assessment === "within_comparables") return t(`${base}_within`);
  if (data.assessment === "above_comparables") return t(`${base}_above`, { pct });
  if (data.assessment === "below_comparables") return t(`${base}_below`, { pct });
  return translateAssessmentSummary(data.assessment_summary || "", isRent);
}

function formatCompareBadge(diff, assessment, isRent) {
  const amount = money(Math.abs(diff), isRent);
  const base = isRent ? "valuate_diff" : "valuate_sale_diff";
  if (assessment === "within_comparables") return { text: t(`${base}_within`), tone: "within" };
  if (diff > 0) return { text: t(`${base}_above`, { amount }), tone: "above" };
  if (diff < 0) return { text: t(`${base}_below`, { amount }), tone: "below" };
  return { text: t(`${base}_within`), tone: "within" };
}

function translateAssessmentSummary(text, isRent) {
  if (!text || isEnglish()) return text;
  const above = text.match(
    /^Observed asking price is approximately (\d+)% above the weighted comparable average of (\d+) listings in Dataset ([\w.]+)\.$/
  );
  if (above) return t("assessment_above", { pct: above[1], n: above[2], version: above[3] });
  const below = text.match(
    /^Observed asking price is approximately (\d+)% below the weighted comparable average of (\d+) listings in Dataset ([\w.]+)\.$/
  );
  if (below) return t("assessment_below", { pct: below[1], n: below[2], version: below[3] });
  const within = text.match(
    /^Observed asking price falls within the bootstrap interval of (\d+) comparable listings in Dataset ([\w.]+)\.$/
  );
  if (within) return t("assessment_within", { n: within[1], version: within[2] });
  return text;
}

const MODE_COPY = {
  rent: {
    heroSubKey: "hero_rent",
    askingLabelKey: "asking_rent",
    fairEstimateKey: "valuate_suggested_value",
    comparablesKey: "comparables_rent",
    comparablesChipKey: "comparables_chip_rent",
    rangeKey: "range_95",
    askingSuffix: "€/mo",
    askingMin: 80,
    askingMax: 2500,
    askingStep: 10,
    askingPlaceholder: "720",
    submitKey: "estimate_fair_rent",
    estimateSuffix: "/mo",
    compMedianSuffix: "/mo",
    negDiffLabelKey: "monthly_diff",
    negDiffSuffix: "/mo",
    listingTypeField: "listing_rent_eur",
    countKey: "rent_listings",
    readyKey: "estimate_ready",
    countLabelKey: "rentals",
  },
  sale: {
    heroSubKey: "hero_sale",
    askingLabelKey: "asking_price",
    fairEstimateKey: "valuate_suggested_value",
    comparablesKey: "comparables_sale",
    comparablesChipKey: "comparables_chip_sale",
    rangeKey: "range_95_sale",
    askingSuffix: "€",
    askingMin: 10000,
    askingMax: 500000,
    askingStep: 1000,
    askingPlaceholder: "148000",
    submitKey: "estimate_fair_price",
    estimateSuffix: "",
    compMedianSuffix: "",
    negDiffLabelKey: "price_diff",
    negDiffSuffix: "",
    listingTypeField: "listing_sale_eur",
    countKey: "sale_listings",
    readyKey: "sale_estimate_ready",
    countLabelKey: "sales",
  },
};

function modeCopy() {
  return MODE_COPY[valuationMode];
}

/** Accept both legacy string[] and current object[] from /api/neighborhoods */
function normalizeNeighborhoodOptions(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => {
      if (typeof item === "string") {
        return {
          name: item,
          rent_listings: 0,
          sale_listings: 0,
          estimate_ready: false,
          sale_estimate_ready: false,
        };
      }
      const name = item?.name ?? item?.neighborhood_name ?? "";
      return {
        name: String(name),
        rent_listings: Number(item?.rent_listings ?? 0),
        sale_listings: Number(item?.sale_listings ?? 0),
        estimate_ready: Boolean(item?.estimate_ready),
        sale_estimate_ready: Boolean(item?.sale_estimate_ready),
      };
    })
    .filter((o) => o.name);
}

function track(event, extra = {}) {
  if (window.MetrikTrack) {
    window.MetrikTrack.track(event, { valuation_type: valuationMode, ...lastSearch, ...extra });
    return;
  }
  fetch("/api/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event, valuation_type: valuationMode, municipality: "Prishtina", ...lastSearch, ...extra }),
  }).catch(() => {});
}

function formatNeighborhoodLabel(o) {
  const c = modeCopy();
  const tag = o[c.readyKey] ? "ready" : "limited";
  const count = o[c.countKey];
  return `${o.name}, ${count} ${t(c.countLabelKey)} (${tag === "ready" ? t("ready") : t("limited_data_tag")})`;
}

function renderNeighborhoodList(filter = "") {
  const list = document.getElementById("neighborhood-list");
  const c = modeCopy();
  const q = filter.trim().toLowerCase();
  const matches = neighborhoodData.filter(
    (o) => !q || o.name.toLowerCase().includes(q)
  );

  list.innerHTML = "";
  if (!matches.length) {
    const li = document.createElement("li");
    li.className = "combo-empty";
    li.textContent = t("nh_no_match");
    list.appendChild(li);
    return;
  }

  for (const o of matches) {
    const li = document.createElement("li");
    const ready = o[c.readyKey];
    li.className = ready
      ? "metrik-search-item combo-item ready"
      : "metrik-search-item combo-item limited";
    li.dataset.value = o.name;
    li.role = "option";
    li.tabIndex = -1;
    li.innerHTML = `
      <div class="metrik-search-item-head">
        <span class="metrik-search-entity">${esc(t("search_entity_neighborhood"))}</span>
        <strong class="metrik-search-name">${esc(o.name)}</strong>
      </div>
      <span class="metrik-search-meta">${esc(o[c.countKey])} ${esc(t(c.countLabelKey))} · ${
      ready ? esc(t("ready")) : esc(t("limited_data_tag"))
    }</span>`;
    li.addEventListener("mousedown", (e) => {
      e.preventDefault();
      selectNeighborhood(o);
    });
    list.appendChild(li);
  }
}

function selectNeighborhood(o) {
  if (!o || typeof o !== "object" || !o.name) return;
  const input = document.getElementById("neighborhood-input");
  const hidden = document.getElementById("neighborhood");
  input.value = o.name;
  hidden.value = o.name;
  document.getElementById("neighborhood-list").classList.add("hidden");
  const hint = document.getElementById("nh-hint");
  hint.textContent = formatNeighborhoodLabel(o);
  const c = modeCopy();
  hint.className = o[c.readyKey] ? "hint hint-ready" : "hint hint-limited";
  updatePropertySummaryPreview();
  updateEmptyPreview();
}

function applyValuationMode(mode, { preserveResults = false } = {}) {
  valuationMode = mode === "sale" ? "sale" : "rent";
  if (!preserveResults) lastValuationResult = null;
  const c = modeCopy();

  document.querySelectorAll(".mode-btn").forEach((btn) => {
    const active = btn.dataset.mode === valuationMode;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });

  const sub = document.getElementById("hero-sub");
  if (sub) sub.textContent = t(c.heroSubKey);

  document.getElementById("asking-label").innerHTML =
    `${t(c.askingLabelKey)} <span class="optional">${t("optional")}</span>`;
  const asking = document.getElementById("asking-price");
  if (asking) asking.value = "";
  document.getElementById("asking-suffix").textContent =
    valuationMode === "rent" ? `€${t("per_month_suffix")}` : c.askingSuffix;
  syncAskingSlider();

  document.getElementById("submit-btn").textContent = t(c.submitKey);
  setSuffixVisibility(valuationMode === "rent");
  updateResultLabels(valuationMode);

  document.getElementById("error").classList.add("hidden");
  if (!preserveResults) {
    document.getElementById("results").classList.add("hidden");
    setValuateEmptyVisible(true);
    resetValuationOutput();
  }
  updatePropertySummaryPreview();
  updateEmptyPreview();

  const selected = document.getElementById("neighborhood").value;
  if (selected) {
    const o = neighborhoodData.find((n) => n.name === selected);
    if (o) selectNeighborhood(o);
  } else {
    const hint = document.getElementById("nh-hint");
    const ready = neighborhoodData.filter((o) => o[c.readyKey]).length;
    hint.textContent = `${ready} ready for ${valuationMode} · ${neighborhoodData.length} neighborhoods`;
  }

  const url = new URL(window.location.href);
  url.searchParams.set("type", valuationMode);
  window.history.replaceState({}, "", url);
}

function setupModeToggle() {
  document.querySelectorAll(".mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.mode !== valuationMode) applyValuationMode(btn.dataset.mode);
    });
  });

  const params = new URLSearchParams(window.location.search);
  applyValuationMode(params.get("type") === "sale" ? "sale" : "rent", { preserveResults: true });
}

function setupNeighborhoodCombo() {
  const input = document.getElementById("neighborhood-input");
  const list = document.getElementById("neighborhood-list");
  const combo = document.getElementById("neighborhood-combo");

  input.addEventListener("focus", () => {
    renderNeighborhoodList(input.value);
    list.classList.remove("hidden");
  });

  input.addEventListener("input", () => {
    document.getElementById("neighborhood").value = "";
    renderNeighborhoodList(input.value);
    list.classList.remove("hidden");
  });

  document.addEventListener("click", (e) => {
    if (!combo.contains(e.target)) {
      list.classList.add("hidden");
      syncNeighborhoodFromInput();
    }
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      list.classList.add("hidden");
      input.blur();
    }
    if (e.key === "Enter") {
      const first = list.querySelector(".metrik-search-item:not(.combo-empty)");
      if (first && !document.getElementById("neighborhood").value) {
        e.preventDefault();
        const name = first.dataset.value;
        const o = neighborhoodData.find((n) => n.name === name);
        if (o) selectNeighborhood(o);
      }
    }
  });
}

function syncNeighborhoodFromInput() {
  const raw = document.getElementById("neighborhood-input").value.trim();
  if (!raw) return;
  const rawName = raw.split("-")[0].trim();
  const exact = neighborhoodData.find(
    (o) => o.name.toLowerCase() === raw.toLowerCase() || o.name.toLowerCase() === rawName.toLowerCase()
  );
  if (exact) {
    selectNeighborhood(exact);
    return;
  }
  const partial = neighborhoodData.filter(
    (o) =>
      o.name.toLowerCase().includes(raw.toLowerCase()) ||
      o.name.toLowerCase().includes(rawName.toLowerCase())
  );
  if (partial.length === 1) {
    selectNeighborhood(partial[0]);
  }
}

async function waitForValuationReady() {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    try {
      const res = await apiFetch("/api/ready", {}, 5000);
      if (res.ok) {
        const health = await res.json();
        if (health.comparables_ready) return { ready: true, health };
      } else if (res.status === 404 && neighborhoodData.length > 0) {
        // Older API build without /api/ready, neighborhoods cache implies server is up.
        return { ready: true, health: null };
      }
    } catch {
      /* server still starting */
    }
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  return { ready: false, health: null };
}

function setSubmitEnabled(enabled, hint) {
  const submitBtn = document.getElementById("submit-btn");
  if (submitBtn) submitBtn.disabled = !enabled;
  if (hint) {
    const hintEl = document.getElementById("nh-hint");
    if (hintEl) hintEl.textContent = hint;
  }
}

async function apiFetch(url, options = {}, timeoutMs = 30000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function loadNeighborhoods() {
  const hint = document.getElementById("nh-hint");
  try {
    let rows;
    if (window.MetrikApiCache) {
      rows = await window.MetrikApiCache.getJson("/api/neighborhoods", { ttlMs: 120_000 });
    } else {
      const res = await apiFetch("/api/neighborhoods");
      if (!res.ok) {
        hint.textContent = t("valuate_nh_load_error");
        return;
      }
      rows = await res.json();
    }
    neighborhoodData = normalizeNeighborhoodOptions(rows);
  } catch (err) {
    const aborted = err && err.name === "AbortError";
    hint.textContent = aborted
      ? t("valuate_nh_timeout")
      : t("valuate_nh_load_error");
    return;
  }

  if (!neighborhoodData.length) {
    hint.textContent = t("valuate_nh_empty");
    return;
  }

  const c = modeCopy();
  const ready = neighborhoodData.filter((o) => o[c.readyKey]).length;
  const totalListings = neighborhoodData.reduce((sum, o) => sum + o[c.countKey], 0);
  if (totalListings === 0) {
    hint.textContent =
      valuationMode === "rent"
        ? t("valuate_no_rent_data")
        : t("valuate_no_sale_data");
    hint.className = "hint hint-limited";
  } else {
    hint.textContent = t("valuate_nh_ready", {
      ready,
      total: neighborhoodData.length,
    });
  }

  const prefill = new URLSearchParams(window.location.search);
  const prefillNh = prefill.get("neighborhood");
  const prefillMatch = prefillNh
    ? neighborhoodData.find((o) => o.name.toLowerCase() === prefillNh.toLowerCase())
    : null;

  const defaultNh =
    prefillMatch ||
    neighborhoodData.find((o) => o.name === "Ulpiana" && o[c.readyKey]) ||
    neighborhoodData.find((o) => o.name === "Ulpiana") ||
    neighborhoodData.find((o) => o[c.readyKey]) ||
    neighborhoodData[0];
  selectNeighborhood(defaultNh);

  const prefillArea = prefill.get("area");
  if (prefillArea) {
    syncAreaSlider(prefillArea);
  } else {
    syncAreaSlider(document.getElementById("area")?.value || 78);
  }
  const prefillBeds = prefill.get("bedrooms");
  if (prefillBeds) {
    const bedsEl = document.getElementById("bedrooms");
    if (bedsEl) bedsEl.value = prefillBeds;
  }

  setupNeighborhoodCombo();
  wireValuateSliders();
  ["neighborhood-input", "area", "bedrooms", "asking-price"].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("input", updatePropertySummaryPreview);
    el.addEventListener("change", updatePropertySummaryPreview);
  });
  syncAskingSlider();
  updatePropertySummaryPreview();
  updateEmptyPreview();

  const warm = await waitForValuationReady();
  if (!warm.ready) {
    setSubmitEnabled(
      true,
      "Valuation data may still be loading, you can try now; if it is not ready, Metrik will show the server message."
    );
    return;
  }
  setSubmitEnabled(true);
}

function parseApiDetail(data) {
  if (!data || data.detail == null) return null;
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail
      .map((item) => (typeof item === "string" ? item : item?.msg))
      .filter(Boolean)
      .join(" ");
  }
  return String(data.detail);
}

function bedroomLabel(beds) {
  if (beds === "" || beds == null) return null;
  const n = Number(beds);
  if (n === 0) return t("studio");
  return t("bedrooms_count", { n });
}

function formatValuationEuro(amount, isRent) {
  if (amount == null || Number.isNaN(Number(amount))) return "—";
  const suffix = isRent ? t("per_month_suffix") : "";
  const fmt = isRent ? window.MetrikFormat.euroRent : window.MetrikFormat.euroSale;
  return `${fmt(amount)}${suffix}`;
}

function renderSummaryChips(container, { neighborhood, area, bedrooms, compCount = null }) {
  if (!container) return;
  const chips = [];
  if (neighborhood) chips.push({ text: neighborhood });
  if (area) chips.push({ text: `${area} m²` });
  const bedText = bedroomLabel(bedrooms);
  if (bedText) chips.push({ text: bedText });
  chips.push({
    text: valuationMode === "rent" ? t("valuate_mode_rent") : t("valuate_mode_sale"),
  });
  if (compCount != null) {
    chips.push({ text: t("comparables_chip", { n: compCount }), muted: true });
  }

  container.innerHTML = "";
  for (const chip of chips) {
    const span = document.createElement("span");
    span.className = `property-summary-chip${chip.muted ? " property-summary-chip-muted" : ""}`;
    span.textContent = chip.text;
    container.appendChild(span);
  }
  container.hidden = chips.length === 0;
}

function updateEmptyPreview() {
  const isRent = valuationMode === "rent";
  const suffix = isRent ? t("per_month_suffix") : "";
  const est = document.getElementById("preview-estimate");
  if (est) est.textContent = `€—${suffix}`;
  const range = document.getElementById("preview-range");
  if (range) range.textContent = `€— – €—${suffix}`;
}

function updatePropertySummaryPreview() {
  const container = document.getElementById("property-summary-preview");
  if (!container) return;
  const neighborhood =
    document.getElementById("neighborhood").value ||
    document.getElementById("neighborhood-input").value.trim();
  const area = document.getElementById("area").value;
  const bedrooms = document.getElementById("bedrooms").value;

  const chips = [
    {
      text: neighborhood || t("valuate_chip_nh_pending"),
      placeholder: !neighborhood,
    },
    {
      text: area ? `${area} m²` : t("valuate_chip_area_pending"),
      placeholder: !area,
    },
    {
      text: bedroomLabel(bedrooms) || t("valuate_chip_beds_pending"),
      placeholder: !bedroomLabel(bedrooms),
    },
    {
      text: valuationMode === "rent" ? t("valuate_mode_rent") : t("valuate_mode_sale"),
    },
  ];

  container.innerHTML = "";
  for (const chip of chips) {
    const span = document.createElement("span");
    span.className = `property-summary-chip${chip.placeholder ? " property-summary-chip-placeholder" : ""}`;
    span.textContent = chip.text;
    container.appendChild(span);
  }
}

function renderEvidenceChips(container, lines) {
  if (!container) return;
  container.innerHTML = "";
  for (const line of lines || []) {
    if (/^\d+ comparable apartments$/.test(line)) continue;
    const chip = document.createElement("span");
    chip.className = "evidence-chip";
    chip.textContent = translateWhyCheck(line);
    container.appendChild(chip);
  }
}

function renderValueDrivers(factors) {
  const section = document.getElementById("drivers-section");
  const container = document.getElementById("value-drivers");
  if (!section || !container) return;
  const items = (factors || []).map(translateFactor).filter(Boolean);
  container.innerHTML = "";
  for (const text of items) {
    const chip = document.createElement("span");
    chip.className = "evidence-chip";
    chip.textContent = text;
    container.appendChild(chip);
  }
  section.hidden = items.length === 0;
}

function renderCompPreview(comparables, isRent, neighborhoodName) {
  const section = document.getElementById("comp-preview-section");
  const container = document.getElementById("comp-preview");
  if (!section || !container) return;
  const top = (comparables || []).slice(0, 3);
  container.innerHTML = "";
  for (const comp of top) {
    const card = document.createElement("div");
    card.className = "comp-preview-card";
    const br =
      comp.bedrooms != null
        ? comp.bedrooms === 0
          ? t("studio")
          : t("bedrooms_count", { n: comp.bedrooms })
        : t("valuate_unknown_beds");
    const loc = neighborhoodName ? `${esc(neighborhoodName)} · ` : "";
    card.innerHTML = `
      <span class="comp-preview-price">${
        isRent ? window.MetrikFormat.euroRent(comp.rent_eur) : window.MetrikFormat.euroSale(comp.rent_eur)
      }${isRent ? esc(t("per_month_suffix")) : ""}</span>
      <span class="comp-preview-meta">${loc}${esc(window.MetrikFormat.areaListing(comp.area_sqm))} · ${esc(br)}</span>
    `;
    container.appendChild(card);
  }
  section.hidden = top.length === 0;
}

function renderMarketDelta(data, askingPrice, isRent) {
  const pctEl = document.getElementById("market-delta-pct");
  const amtEl = document.getElementById("market-delta-amt");
  const compareBlock = document.getElementById("compare-block");
  if (!pctEl || !amtEl) return;

  const pct = Math.abs(Math.round(data.vs_median_pct ?? 0));
  if (data.assessment === "within_comparables") {
    pctEl.textContent = t("valuate_market_delta_pct_within");
    pctEl.className = "market-delta-pct within";
    compareBlock?.classList.remove("below-market");
  } else if (data.assessment === "above_comparables") {
    pctEl.textContent = t("valuate_market_delta_pct_above", { pct });
    pctEl.className = "market-delta-pct above";
    compareBlock?.classList.remove("below-market");
  } else if (data.assessment === "below_comparables") {
    pctEl.textContent = t("valuate_market_delta_pct_below", { pct });
    pctEl.className = "market-delta-pct below";
    compareBlock?.classList.add("below-market");
  } else {
    pctEl.textContent = "";
    pctEl.className = "market-delta-pct";
    compareBlock?.classList.remove("below-market");
  }

  const medianDiff =
    data.negotiation?.monthly_difference_eur ?? askingPrice - data.comparable_median_rent_eur;
  if (medianDiff > 0) {
    const key = isRent ? "valuate_market_delta_amount_above" : "valuate_market_delta_amount_sale_above";
    amtEl.textContent = t(key, { amount: money(Math.abs(medianDiff), isRent) });
    amtEl.className = "market-delta-amt above";
  } else if (medianDiff < 0) {
    const key = isRent ? "valuate_market_delta_amount_below" : "valuate_market_delta_amount_sale_below";
    amtEl.textContent = t(key, { amount: money(Math.abs(medianDiff), isRent) });
    amtEl.className = "market-delta-amt below";
  } else {
    amtEl.textContent = "";
    amtEl.className = "market-delta-amt";
  }
}

function renderMarketContext(data, isRent) {
  setText("context-median", formatValuationEuro(data.comparable_median_rent_eur, isRent));
  setText("context-yours", formatValuationEuro(data.point_estimate_eur, isRent));

  let position = t("valuate_context_within");
  const comps = data.comparables || [];
  if (comps.length >= 4) {
    const prices = comps.map((c) => c.rent_eur).sort((a, b) => a - b);
    const q75 = prices[Math.floor(prices.length * 0.75)];
    if (data.point_estimate_eur >= q75) {
      position = t("valuate_context_top_quartile");
    } else if (data.point_estimate_eur > data.comparable_median_rent_eur * 1.03) {
      position = t("valuate_context_above");
    } else if (data.point_estimate_eur < data.comparable_median_rent_eur * 0.97) {
      position = t("valuate_context_below");
    }
  } else if (data.point_estimate_eur > data.comparable_median_rent_eur * 1.03) {
    position = t("valuate_context_above");
  } else if (data.point_estimate_eur < data.comparable_median_rent_eur * 0.97) {
    position = t("valuate_context_below");
  }
  setText("context-position", position);
}

function setValuateEmptyVisible(visible) {
  const empty = document.getElementById("valuate-empty");
  if (empty) empty.classList.toggle("hidden", !visible);
}

function showError(msg, { title = null, hint = null } = {}) {
  title = title || t("could_not_estimate");
  document.getElementById("error-title").textContent = title;
  document.getElementById("error-msg").textContent = msg;
  const hintEl = document.getElementById("error-hint");
  if (hint) {
    hintEl.textContent = hint;
    hintEl.classList.remove("hidden");
  } else {
    hintEl.classList.add("hidden");
  }
  document.getElementById("error").classList.remove("hidden");
  document.getElementById("results").classList.add("hidden");
  setValuateEmptyVisible(true);
  track("valuation_abandon", { success: false });
}

function renderResult(data) {
  lastValuationResult = data;
  const isRent = isRentResult(data);
  const kind = isRent ? "rent" : "sale";
  updateResultLabels(kind);
  setSuffixVisibility(isRent);

  document.getElementById("error").classList.add("hidden");
  document.getElementById("results").classList.remove("hidden");
  setValuateEmptyVisible(false);

  renderEstimateValue(data.point_estimate_eur, isRent);
  const rangeLine = document.getElementById("range-line");
  if (rangeLine) {
    rangeLine.textContent = `€${money(data.lower_ci_eur, isRent)}–${money(data.upper_ci_eur, isRent)}${
      isRent ? t("per_month_suffix") : ""
    }`;
  }
  const psmLine = document.getElementById("price-psm-line");
  if (psmLine) {
    if (!isRent && data.median_rent_per_sqm) {
      psmLine.textContent = t("sale_price_psm", {
        psm: window.MetrikFormat.int(window.MetrikFormat.roundSalePsm(data.median_rent_per_sqm)),
      });
      psmLine.classList.remove("hidden");
    } else {
      psmLine.classList.add("hidden");
    }
  }

  const confidenceBadge = document.getElementById("confidence-badge");
  if (confidenceBadge) {
    confidenceBadge.textContent = translateConfidenceLabel(data.confidence_label);
  }
  const basedOn = document.getElementById("based-on-line");
  if (basedOn) {
    basedOn.textContent = t("valuate_based_on", { n: data.comparable_count });
  }

  renderSummaryChips(document.getElementById("property-summary"), {
    neighborhood: data.neighborhood_name,
    area: Math.round(data.area_sqm),
    bedrooms: data.bedrooms ?? "",
    compCount: data.comparable_count,
  });
  const summary = document.getElementById("property-summary");
  if (summary) summary.hidden = false;

  setText("comp-count", data.comparable_count);
  setText("method", translateMethodSummary(data.method_summary));
  setText("dataset", data.dataset_version);
  const factors = data.explanation?.top_factors || [];
  const excluded = data.explanation?.excluded || [];
  setText("factors", factors.map(translateFactor).join(", "));
  setText("excluded", excluded.map(translateExcluded).join("; "));

  renderEvidenceChips(document.getElementById("why-checks"), data.why_checks);
  renderMarketContext(data, isRent);
  renderCompPreview(data.comparables, isRent, data.neighborhood_name);
  renderValueDrivers(factors);

  const compareBlock = document.getElementById("compare-block");
  const askingPrice = isRent
    ? data.listing_rent_eur ?? data.negotiation?.listing_rent_eur
    : data.listing_sale_eur ?? data.negotiation?.listing_rent_eur;
  if (askingPrice && data.negotiation) {
    compareBlock.classList.remove("hidden");
    renderMarketDelta(data, askingPrice, isRent);
    setText("neg-listing", money(askingPrice, isRent));
    setText("compare-fair", money(data.point_estimate_eur, isRent));
    setText("neg-lo", money(data.negotiation.negotiation_lo_eur, isRent));
    setText("neg-hi", money(data.negotiation.negotiation_hi_eur, isRent));
    const diff = askingPrice - data.point_estimate_eur;
    const badge = formatCompareBadge(diff, data.assessment, isRent);
    const badgeEl = document.getElementById("compare-badge");
    badgeEl.textContent = badge.text;
    badgeEl.className = `compare-badge ${badge.tone}`;
    setText("assessment", translateAssessmentShort(data, isRent));
  } else {
    compareBlock.classList.add("hidden");
  }

  const lim = document.getElementById("limitations");
  lim.innerHTML = "";
  for (const note of data.confidence_notes || []) {
    const li = document.createElement("li");
    li.textContent = translateConfidenceNote(note);
    lim.appendChild(li);
  }

  const list = document.getElementById("comparables");
  list.innerHTML = "";
  for (const comp of data.comparables || []) {
    const li = document.createElement("li");
    const br =
      comp.bedrooms != null
        ? comp.bedrooms === 0
          ? t("studio")
          : t("bedrooms_count", { n: comp.bedrooms })
        : t("valuate_unknown_beds");
    li.textContent = `${window.MetrikFormat.areaListing(comp.area_sqm)} · ${br} · ${
      isRent ? window.MetrikFormat.euroRent(comp.rent_eur) : window.MetrikFormat.euroSale(comp.rent_eur)
    }${isRent ? t("per_month_suffix") : ""}`;
    list.appendChild(li);
  }

  track("valuation_completed", { success: true, property_type: "apartment" });
  renderNextSteps(data);
}

function renderNextSteps(data) {
  const panel = document.getElementById("valuate-next-steps");
  if (!panel || !data?.neighborhood_name) return;
  const nh = data.neighborhood_name;
  const compareHref = `/compare?nh=${encodeURIComponent(nh)}`;
  const lead = document.getElementById("valuate-next-steps-lead");
  const compareLink = document.getElementById("valuate-next-compare");
  if (lead) lead.textContent = t("valuate_next_steps_lead", { nh });
  if (compareLink) compareLink.href = compareHref;
  panel.classList.remove("hidden");
}

["comparables", "methodology", "limitations"].forEach((section) => {
  const el = document.getElementById(`details-${section}`);
  if (!el) return;
  el.addEventListener("toggle", () => {
    if (el.open) track("section_expand", { section });
  });
});

document.getElementById("estimate-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  syncNeighborhoodFromInput();

  const neighborhood = document.getElementById("neighborhood").value;
  if (!neighborhood) {
    showError(t("valuate_pick_nh"));
    document.getElementById("neighborhood-list").classList.remove("hidden");
    renderNeighborhoodList(document.getElementById("neighborhood-input").value);
    return;
  }

  const c = modeCopy();
  const body = {
    valuation_type: valuationMode,
    neighborhood,
    area_sqm: Number(document.getElementById("area").value),
  };
  const beds = document.getElementById("bedrooms").value;
  if (beds !== "") body.bedrooms = Number(beds);
  const asking = document.getElementById("asking-price").value;
  if (asking) body[c.listingTypeField] = Number(asking);

  lastSearch = {
    neighborhood: body.neighborhood,
    area_sqm: body.area_sqm,
    bedrooms: body.bedrooms ?? null,
    had_asking: !!asking,
  };
  track("valuation_requested", { property_type: "apartment", listing_type: valuationMode });

  const submitBtn = document.getElementById("submit-btn");
  const submitLabel = submitBtn.textContent;
  submitBtn.disabled = true;
  submitBtn.textContent = tf("valuate_working", "Estimating…");
  document.getElementById("error").classList.add("hidden");
  document.getElementById("results").classList.add("hidden");
  setValuateEmptyVisible(true);
  const emptyPanel = document.getElementById("valuate-empty");
  if (emptyPanel) {
    emptyPanel.classList.add("is-skeleton-loading");
    emptyPanel.setAttribute("aria-busy", "true");
  }
  resetValuationOutput();

  try {
    const res = await apiFetch(
      "/api/valuate",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
      30000
    );
    const text = await res.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      showError(t("valuate_server_error_msg", { status: res.status }), {
        title: t("valuate_server_error"),
        hint: t("valuate_server_error_hint"),
      });
      return;
    }
    if (!res.ok) {
      const detail = parseApiDetail(data) || t("valuate_could_not_produce");
      const insufficient = /insufficient evidence/i.test(detail);
      const dbUnavailable = /database unavailable/i.test(detail);
      const warming = res.status === 503 && !dbUnavailable && /still loading/i.test(detail);
      showError(detail, {
        title: dbUnavailable
          ? t("valuate_db_unavailable")
          : warming
            ? t("valuate_still_loading")
            : insufficient
              ? t("valuate_insufficient_evidence")
              : t("could_not_estimate"),
        hint: dbUnavailable
          ? t("valuate_db_unavailable_hint")
          : warming
            ? t("valuate_timeout_hint")
            : insufficient
              ? t("error_hint")
              : null,
      });
      return;
    }
    try {
      renderResult(data);
    } catch (renderErr) {
      console.error("renderResult failed", renderErr, data);
      showError(t("valuate_display_error_msg"), {
        title: t("valuate_display_error"),
        hint: String(renderErr?.message || renderErr),
      });
      return;
    }
    document.getElementById("valuate-output-col")?.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    console.error("valuate request failed", err);
    const aborted = err && err.name === "AbortError";
    showError(
      aborted ? t("valuate_request_timeout_msg") : t("valuate_connection_error_msg"),
      {
        title: aborted ? t("valuate_request_timeout") : t("valuate_connection_error"),
        hint: aborted ? t("valuate_timeout_hint") : t("valuate_connection_hint"),
      }
    );
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = submitLabel;
    if (emptyPanel) {
      emptyPanel.classList.remove("is-skeleton-loading");
      emptyPanel.setAttribute("aria-busy", "false");
    }
  }
});

document.addEventListener("metrik:langchange", () => {
  window.MetrikI18n.apply();
  applyValuationMode(valuationMode, { preserveResults: true });
  updateEmptyPreview();
  if (lastValuationResult) renderResult(lastValuationResult);
});

setupModeToggle();
loadNeighborhoods();
