const t = (k) => window.MetrikI18n.t(k);

function value(id) {
  return document.getElementById(id)?.value.trim() || "";
}

function optionalNumber(id) {
  const raw = value(id);
  return raw ? Number(raw) : undefined;
}

function compactPayload(payload) {
  return Object.fromEntries(
    Object.entries(payload).filter(([, v]) => v !== "" && v !== undefined && v !== null)
  );
}

function showStatus(message, ok = true) {
  const el = document.getElementById("contact-status");
  el.textContent = message;
  el.className = ok ? "hint contact-status status-ok" : "hint contact-status status-error";
}

function setBusy(form, busy) {
  const button = form.querySelector("button[type='submit']");
  if (!button) return;
  if (!button.dataset.originalText) button.dataset.originalText = button.textContent;
  button.disabled = busy;
  button.textContent = busy ? t("contact_sending") : button.dataset.originalText;
}

async function submitJson(form, url, payload, successMessage) {
  setBusy(form, true);
  showStatus("", true);
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(compactPayload(payload)),
    });
    if (!res.ok) {
      let detail = t("contact_error");
      try {
        const data = await res.json();
        detail = Array.isArray(data.detail)
          ? data.detail.map((item) => item.msg || item).join(" ")
          : data.detail || detail;
      } catch {
        /* keep generic message */
      }
      showStatus(detail, false);
      return;
    }
    form.reset();
    showStatus(successMessage, true);
  } catch {
    showStatus(t("contact_error"), false);
  } finally {
    setBusy(form, false);
  }
}

function activateTab(tab) {
  document.querySelectorAll(".contact-tabs .mode-btn").forEach((btn) => {
    const active = btn.dataset.tab === tab;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  document.querySelectorAll(".contact-pane").forEach((pane) => {
    pane.classList.toggle("hidden", pane.dataset.pane !== tab);
  });
  showStatus("", true);
  const url = new URL(window.location.href);
  url.searchParams.set("tab", tab);
  window.history.replaceState({}, "", url);
}

document.querySelectorAll(".contact-tabs .mode-btn").forEach((btn) => {
  btn.addEventListener("click", () => activateTab(btn.dataset.tab));
});

document.getElementById("contact-form").addEventListener("submit", (e) => {
  e.preventDefault();
  submitJson(
    e.currentTarget,
    "/api/contact",
    {
      name: value("contact-name"),
      email: value("contact-email"),
      topic: value("contact-topic"),
      message: value("contact-message"),
    },
    t("contact_success")
  );
});

document.getElementById("report-form").addEventListener("submit", (e) => {
  e.preventDefault();
  submitJson(
    e.currentTarget,
    "/api/public-report",
    {
      issue: value("report-issue"),
      page_url: value("report-page-url"),
      listing_url: value("report-listing-url"),
      email: value("report-email"),
      message: value("report-message"),
    },
    t("report_success")
  );
});

document.getElementById("listing-form").addEventListener("submit", (e) => {
  e.preventDefault();
  submitJson(
    e.currentTarget,
    "/api/listing-submissions",
    {
      submitter_email: value("listing-email"),
      listing_url: value("listing-url"),
      source: value("listing-source"),
      listing_type: value("listing-type"),
      property_type: value("listing-property-type"),
      city: "Prishtina",
      neighborhood: value("listing-neighborhood"),
      street: value("listing-street"),
      price_eur: optionalNumber("listing-price"),
      area_sqm: optionalNumber("listing-area"),
      bedrooms: optionalNumber("listing-bedrooms"),
      notes: value("listing-notes"),
    },
    t("listing_success")
  );
});

const initialTab = new URLSearchParams(window.location.search).get("tab");
if (["contact", "report", "listing"].includes(initialTab)) {
  activateTab(initialTab);
}
