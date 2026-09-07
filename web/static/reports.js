const t = (k) => window.MetrikI18n.t(k);
const esc = (v) => window.MetrikSanitize.escapeHtml(v);

function formatDate(iso) {
  if (!iso) return "";
  const lang = window.MetrikI18n.getLang() === "sq" ? "sq-AL" : "en";
  return new Date(iso).toLocaleDateString(lang, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

function renderReports(reports) {
  const list = document.getElementById("report-list");
  const loading = document.getElementById("reports-loading");
  const featured = document.getElementById("featured-content");
  loading.classList.add("hidden");

  if (!reports.length) {
    loading.textContent = t("no_reports");
    loading.classList.remove("hidden");
    return;
  }

  featured.classList.remove("hidden");
  document.getElementById("featured-title").textContent = "Raporti Vjetor i Tregut";
  document.getElementById("featured-meta").textContent = "Dashboard Interaktiv";
  document.getElementById("featured-desc").textContent = "Përmbledhje vizuale dhe statistikore e tregut për 12 muajt e fundit.";
  
  const flink = document.getElementById("featured-link");
  flink.href = "/annual";
  flink.className = "btn-secondary";
  flink.style.cssText = "display: inline-block; padding: 0.3rem 1rem; font-size: 0.85rem; border-radius: 20px;";
  flink.textContent = t("read_report");

  list.innerHTML = "";
  for (const r of reports) {
    const li = document.createElement("li");
    li.className = "report-list-item";
    li.innerHTML = `
      <div>
        <strong>${esc(r.title)}</strong>
        <span class="report-list-meta">${esc(r.type)} · ${esc(formatDate(r.date))}</span>
        <p class="report-list-desc">${esc(r.description)}</p>
      </div>
      <a href="${esc(r.url)}" class="btn-secondary">${esc(t("read"))}</a>
    `;
    list.appendChild(li);
  }
}

async function loadReports() {
  try {
    const res = await fetch("/api/reports");
    if (!res.ok) throw new Error("failed");
    const data = await res.json();
    renderReports(data.reports || []);
  } catch {
    const loading = document.getElementById("reports-loading");
    if (loading) loading.textContent = t("reports_unavailable");
  }
}

document.addEventListener("metrik:langchange", loadReports);
loadReports();
