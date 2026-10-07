const t = (k, v) => window.MetrikI18n.t(k, v);

window.MetrikSearch?.init({
  input: document.getElementById("market-search"),
  list: document.getElementById("search-results"),
  hint: document.getElementById("search-hint"),
  root: document.getElementById("home-search"),
  minChars: 2,
  section: "homepage",
});

// Homepage trust strip. /api/meta is the source of truth; the static snapshot
// is used only when the API is unavailable, because it can lag a new release.
const TRUST_SNAPSHOT_URL = "/static/home-trust.json";
let currentTrust = null;

function animateCount(el, target) {
  const durationMs = 900;
  const start = performance.now();
  const fmt = window.MetrikFormat;
  function frame(now) {
    const progress = Math.min((now - start) / durationMs, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    const value = Math.round(target * eased);
    el.textContent = fmt.int(value);
    if (progress < 1) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

function trustFromMeta(meta) {
  const listings = Number(meta?.active_listings);
  if (!Number.isFinite(listings) || listings <= 0) return null;
  return {
    source: "meta",
    active_listings: listings,
    updated_at: meta.corpus_updated_at || meta.data_through || null,
  };
}

function trustFromSnapshot(snap) {
  const listings = Number(snap?.active_listings);
  if (!Number.isFinite(listings) || listings <= 0 || typeof snap?.updated_at !== "string") {
    return null;
  }
  return { source: "snapshot", active_listings: listings, updated_at: snap.updated_at };
}

function renderTrustStrip(trust, { animate }) {
  const strip = document.getElementById("home-trust-strip");
  if (!strip) return;
  const listingsEl = document.getElementById("trust-listings");
  const updatedEl = document.getElementById("trust-updated");
  if (!listingsEl || !updatedEl) return;

  if (!trust) {
    strip.hidden = true;
    return;
  }
  const fmt = window.MetrikFormat;
  listingsEl.classList.remove("skel-chip");
  updatedEl.classList.remove("skel-chip");
  listingsEl.removeAttribute("aria-hidden");
  updatedEl.removeAttribute("aria-hidden");
  strip.dataset.source = trust.source;

  if (animate) {
    animateCount(listingsEl, trust.active_listings);
  } else {
    listingsEl.textContent = fmt.int(trust.active_listings);
  }
  updatedEl.textContent = trust.updated_at ? fmt.dateShort(trust.updated_at) : "";
  strip.hidden = false;
}

async function fetchMeta() {
  if (window.MetrikCorpusMeta) return window.MetrikCorpusMeta;
  if (window.MetrikSite?.fetchCorpusMeta) return window.MetrikSite.fetchCorpusMeta();
  const res = await fetch("/api/meta");
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return res.json();
}

async function loadSnapshotTrust() {
  try {
    const res = await fetch(TRUST_SNAPSHOT_URL);
    if (!res.ok) return null;
    return trustFromSnapshot(await res.json());
  } catch {
    return null;
  }
}

async function loadTrust() {
  try {
    const fromMeta = trustFromMeta(await fetchMeta());
    if (fromMeta) return fromMeta;
  } catch {
    /* fall back to the static snapshot */
  }
  return loadSnapshotTrust();
}

function applyTrust(trust) {
  if (currentTrust?.source === "meta" && trust?.source !== "meta") return;
  const unchanged =
    currentTrust &&
    trust &&
    currentTrust.source === trust.source &&
    currentTrust.active_listings === trust.active_listings &&
    currentTrust.updated_at === trust.updated_at;
  if (unchanged) return;
  currentTrust = trust;
  renderTrustStrip(trust, { animate: true });
}

loadTrust().then(applyTrust);

document.addEventListener("corpus-meta", (e) => {
  const fromMeta = trustFromMeta(e.detail);
  if (fromMeta) applyTrust(fromMeta);
});

document.addEventListener("metrik:langchange", () => {
  if (currentTrust) renderTrustStrip(currentTrust, { animate: false });
});
