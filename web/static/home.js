const t = (k, v) => window.MetrikI18n.t(k, v);

window.MetrikSearch?.init({
  input: document.getElementById("market-search"),
  list: document.getElementById("search-results"),
  hint: document.getElementById("search-hint"),
  root: document.getElementById("home-search"),
  minChars: 2,
  section: "homepage",
});

// Static homepage trust strip (no API compute at runtime).
const STATIC_TRUST_FALLBACK = {
  active_listings: 8590,
  updated_at: "2026-06-16",
};

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

function renderTrustStripFromMeta(meta) {
  const strip = document.getElementById("home-trust-strip");
  if (!strip || !meta) return;
  const fmt = window.MetrikFormat;
  const listingsEl = document.getElementById("trust-listings");
  const updatedEl = document.getElementById("trust-updated");
  if (!listingsEl || !updatedEl) return;

  if (meta.active_listings) {
    animateCount(listingsEl, Number(meta.active_listings));
  }
  if (meta.corpus_updated_at) {
    updatedEl.textContent = fmt.dateShort(meta.corpus_updated_at);
  }
  strip.hidden = false;
}

function renderTrustStripStatic() {
  const strip = document.getElementById("home-trust-strip");
  if (!strip) return;
  const fmt = window.MetrikFormat;
  const listingsEl = document.getElementById("trust-listings");
  const updatedEl = document.getElementById("trust-updated");

  if (!listingsEl || !updatedEl) return;
  animateCount(listingsEl, STATIC_TRUST_FALLBACK.active_listings);
  updatedEl.textContent = fmt.dateShort(STATIC_TRUST_FALLBACK.updated_at);
  strip.hidden = false;
}

async function loadStaticTrustSnapshot() {
  try {
    const res = await fetch("/static/home-trust.json");
    if (!res.ok) return;
    const snap = await res.json();
    if (
      Number.isFinite(Number(snap?.active_listings)) &&
      typeof snap?.updated_at === "string"
    ) {
      STATIC_TRUST_FALLBACK.active_listings = Number(snap.active_listings);
      STATIC_TRUST_FALLBACK.updated_at = snap.updated_at;
    }
  } catch {
    /* keep fallback */
  }
}

document.addEventListener("metrik:langchange", renderTrustStripStatic);
document.addEventListener("corpus-meta", (e) => renderTrustStripFromMeta(e.detail));
loadStaticTrustSnapshot().finally(renderTrustStripStatic);
if (window.MetrikCorpusMeta) renderTrustStripFromMeta(window.MetrikCorpusMeta);
