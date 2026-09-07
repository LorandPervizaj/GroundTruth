/** Sample-size confidence badges, shared across market + statistics pages. */
(function () {
  const t = (k, v) => window.MetrikI18n.t(k, v);

  const TIER_KEY = {
    high: "conf_tier_high",
    medium: "conf_tier_medium",
    low: "conf_tier_low",
    insufficient: "conf_tier_insufficient",
  };

  function tierLabel(level) {
    return t(TIER_KEY[level] || "conf_tier_insufficient");
  }

  // Plain-language confidence badge. Raw sample size (n) is never shown in the
  // visible label, it lives in the tooltip only. `levelOnly` returns a compact
  // single-word level for dense table cells.
  function badge(sample, { levelOnly = false } = {}) {
    if (!sample?.confidence) return "";
    const level = window.MetrikSanitize.confidenceClass(sample.confidence);
    if (levelOnly) {
      const word = window.MetrikSanitize.escapeHtml(window.MetrikI18n.translateConfidence(level));
      return `<span class="sample-badge confidence-${level}">${word}</span>`;
    }
    const label = tierLabel(level);
    const title =
      sample.n != null
        ? window.MetrikSanitize.escapeAttr(t("conf_tooltip", { tier: label, n: sample.n }))
        : window.MetrikSanitize.escapeAttr(label);
    return `<span class="sample-badge confidence-${level}" title="${title}">${window.MetrikSanitize.escapeHtml(label)}</span>`;
  }

  function rowClass(sample) {
    if (!sample?.confidence) return "";
    if (sample.confidence === "insufficient" || sample.confidence === "low") {
      return "row-confidence-weak";
    }
    return "";
  }

  window.MetrikConfidence = { badge, rowClass, tierLabel };
})();
