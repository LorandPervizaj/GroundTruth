/** Escape API-sourced strings before HTML insertion (stored-XSS defense). */
(function () {
  function escapeHtml(value) {
    if (value == null) return "";
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function pathSegment(value) {
    if (value == null || value === "") return "";
    return encodeURIComponent(String(value));
  }

  function confidenceClass(level) {
    const allowed = ["high", "medium", "low", "insufficient"];
    return allowed.includes(level) ? level : "insufficient";
  }

  window.MetrikSanitize = {
    escapeHtml,
    pathSegment,
    escapeAttr: escapeHtml,
    confidenceClass,
    e: escapeHtml,
    seg: pathSegment,
  };
})();
