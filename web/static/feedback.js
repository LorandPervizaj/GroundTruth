/** Report-a-data-error modal, listing and neighborhood pages. */
(function () {
  const t = (k, v) => window.MetrikI18n.t(k, v);

  const ISSUES = [
    "wrong_price",
    "wrong_location",
    "wrong_area",
    "duplicate",
    "outdated",
    "other",
  ];

  let dialog = null;
  let form = null;
  let messageField = null;
  let issueField = null;
  let contextEl = null;
  let statusEl = null;
  let currentContext = null;

  function ensureDialog() {
    if (dialog) return;
    dialog = document.createElement("dialog");
    dialog.id = "feedback-dialog";
    dialog.className = "feedback-dialog";
    dialog.innerHTML = `
      <form method="dialog" class="feedback-form" id="feedback-form">
        <header class="feedback-header">
          <h2 id="feedback-title"></h2>
          <button type="button" class="feedback-close" id="feedback-close" aria-label="">×</button>
        </header>
        <p class="feedback-context" id="feedback-context"></p>
        <div class="field">
          <label for="feedback-issue" id="feedback-issue-label"></label>
          <select id="feedback-issue" required></select>
        </div>
        <div class="field">
          <label for="feedback-message" id="feedback-message-label"></label>
          <textarea id="feedback-message" rows="3" maxlength="500" placeholder=""></textarea>
        </div>
        <p class="feedback-status hidden" id="feedback-status" role="status"></p>
        <footer class="feedback-actions">
          <button type="button" class="btn-secondary" id="feedback-cancel"></button>
          <button type="submit" class="btn-primary" id="feedback-submit"></button>
        </footer>
      </form>
    `;
    document.body.appendChild(dialog);

    form = dialog.querySelector("#feedback-form");
    messageField = dialog.querySelector("#feedback-message");
    issueField = dialog.querySelector("#feedback-issue");
    contextEl = dialog.querySelector("#feedback-context");
    statusEl = dialog.querySelector("#feedback-status");

    issueField.innerHTML = ISSUES.map(
      (id) => `<option value="${id}">${t(`feedback_issue_${id}`)}</option>`
    ).join("");

    dialog.querySelector("#feedback-close").addEventListener("click", close);
    dialog.querySelector("#feedback-cancel").addEventListener("click", close);
    dialog.addEventListener("click", (e) => {
      if (e.target === dialog) close();
    });
    dialog.addEventListener("close", reset);

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      await submit();
    });
  }

  function applyLabels() {
    if (!dialog) return;
    dialog.querySelector("#feedback-title").textContent = t("feedback_title");
    dialog.querySelector("#feedback-issue-label").textContent = t("feedback_issue_label");
    dialog.querySelector("#feedback-message-label").textContent = t("feedback_message_label");
    messageField.placeholder = t("feedback_message_ph");
    dialog.querySelector("#feedback-cancel").textContent = t("feedback_cancel");
    dialog.querySelector("#feedback-submit").textContent = t("feedback_submit");
    dialog.querySelector("#feedback-close").setAttribute("aria-label", t("close"));
    issueField.innerHTML = ISSUES.map(
      (id) => `<option value="${id}">${t(`feedback_issue_${id}`)}</option>`
    ).join("");
  }

  function contextLabel(ctx) {
    if (ctx.kind === "listing") {
      return t("feedback_context_listing", {
        id: ctx.source_listing_id || "-",
      });
    }
    return t("feedback_context_market", {
      name: ctx.display_name || ctx.slug || "-",
    });
  }

  function open(ctx) {
    ensureDialog();
    applyLabels();
    currentContext = {
      ...ctx,
      page_url: ctx.page_url || window.location.href,
    };
    contextEl.textContent = contextLabel(currentContext);
    issueField.value = ISSUES[0];
    messageField.value = "";
    statusEl.classList.add("hidden");
    statusEl.textContent = "";
    dialog.showModal();
    issueField.focus();
  }

  function close() {
    dialog?.close();
  }

  function reset() {
    currentContext = null;
    if (statusEl) {
      statusEl.classList.add("hidden");
      statusEl.textContent = "";
    }
  }

  async function submit() {
    if (!currentContext) return;
    const payload = {
      kind: currentContext.kind,
      issue: issueField.value,
      message: messageField.value.trim() || null,
      page_url: currentContext.page_url,
      source: currentContext.source,
      source_listing_id: currentContext.source_listing_id,
      listing_url: currentContext.listing_url,
      entity_type: currentContext.entity_type,
      slug: currentContext.slug,
      display_name: currentContext.display_name,
    };
    statusEl.textContent = t("feedback_sending");
    statusEl.classList.remove("hidden");
    try {
      const res = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || t("feedback_error"));
      }
      statusEl.textContent = t("feedback_thanks");
      setTimeout(() => close(), 1200);
      fetch("/api/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event: "data_feedback",
          entity_type: currentContext.entity_type,
          slug: currentContext.slug,
          section: currentContext.kind,
        }),
      }).catch(() => {});
    } catch (err) {
      statusEl.textContent = err.message || t("feedback_error");
    }
  }

  window.MetrikFeedback = { open };
  document.addEventListener("metrik:langchange", applyLabels);
})();
