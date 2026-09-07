const t = (k, v) => window.MetrikI18n.t(k, v);

function canonicalUrl() {
  return `${window.location.origin}/methodology`;
}

function renderMeta(data) {
  const versionEl = document.getElementById("method-version");
  if (versionEl) {
    versionEl.textContent = t("methodology_version_badge", {
      version: data.version,
      released: window.MetrikFormat.dateShort(data.released),
    });
  }

  const citeEl = document.getElementById("method-cite-text");
  if (citeEl) {
    citeEl.textContent = t("methodology_cite_text", {
      version: data.version,
      released: data.released,
      url: canonicalUrl(),
    });
  }

  const freshEl = document.getElementById("method-corpus-freshness");
  if (freshEl && data.corpus_updated_at) {
    freshEl.textContent = t("methodology_corpus_note", {
      date: window.MetrikFormat.dateTime(data.corpus_updated_at),
      n: window.MetrikFormat.int(data.active_listings),
    });
  }

  const freezeEl = document.getElementById("method-dataset-freeze");
  if (freezeEl && data.dataset_version && data.dataset_version !== "live") {
    freezeEl.textContent = t("methodology_dataset_freeze", {
      version: data.dataset_version,
      frozen: data.dataset_frozen_at
        ? window.MetrikFormat.dateShort(data.dataset_frozen_at)
        : "-",
      n: window.MetrikFormat.int(data.active_listings),
      invalid: data.invalid_pct != null ? String(data.invalid_pct) : "-",
      golden: data.golden_accuracy_pct != null ? String(data.golden_accuracy_pct) : "-",
    });
  }
}

async function init() {
  try {
    const res = await fetch("/api/methodology");
    if (!res.ok) return;
    renderMeta(await res.json());
  } catch {
    /* static copy still readable */
  }
}

document.addEventListener("metrik:langchange", init);
init();
