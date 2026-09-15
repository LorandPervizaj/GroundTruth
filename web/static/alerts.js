(function () {
  const t = (key) => window.MetrikI18n.t(key);
  const neighborhood = document.getElementById("alert-neighborhood");
  const listingType = document.getElementById("alert-listing-type");
  const status = document.getElementById("alert-status");
  const emailPanel = document.getElementById("alert-email-panel");
  const alertForm = document.getElementById("alert-form");

  function selectedNeighborhood() {
    const option = neighborhood.selectedOptions[0];
    return option
      ? { slug: option.value, name: option.textContent }
      : null;
  }

  function renderWatchlist() {
    const list = document.getElementById("watchlist-items");
    const empty = document.getElementById("watchlist-empty");
    const items = window.MetrikWatchlist.load();
    list.replaceChildren();
    empty.hidden = items.length > 0;
    for (const item of items) {
      const row = document.createElement("li");
      const link = document.createElement("a");
      link.href = `/market/neighborhood/${encodeURIComponent(item.slug)}`;
      link.textContent = item.display_name;
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "btn-ghost";
      remove.textContent = t("alerts_remove");
      remove.addEventListener("click", () => {
        window.MetrikWatchlist.remove(item.slug);
        renderWatchlist();
      });
      row.append(link, document.createTextNode(" "), remove);
      list.appendChild(row);
    }
  }

  async function loadNeighborhoods() {
    try {
      const response = await fetch("/api/neighborhoods");
      if (!response.ok) throw new Error(`Neighborhood request failed: ${response.status}`);
      const rows = await response.json();
      neighborhood.replaceChildren();
      for (const row of rows) {
        const option = document.createElement("option");
        option.value = row.slug;
        option.textContent = row.name;
        neighborhood.appendChild(option);
      }
    } catch {
      status.textContent = t("valuate_nh_load_error");
    }
  }

  function showEmailUnavailable() {
    if (emailPanel) {
      emailPanel.classList.add("is-unavailable");
    }
    if (alertForm) {
      alertForm.hidden = true;
    }
    const notice = document.getElementById("alert-unavailable");
    if (notice) {
      notice.hidden = false;
      notice.textContent = t("alerts_unavailable");
    }
    status.textContent = "";
  }

  document.getElementById("watchlist-add").addEventListener("click", () => {
    const selected = selectedNeighborhood();
    if (!selected) return;
    window.MetrikWatchlist.add(selected.slug, selected.name, listingType.value);
    renderWatchlist();
    status.textContent = t("alerts_success");
  });

  if (alertForm) {
    alertForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      // Email signup is disabled until notifications exist — never claim success.
      showEmailUnavailable();
      status.textContent = t("alerts_unavailable");
    });
  }

  document.addEventListener("metrik:langchange", () => {
    renderWatchlist();
    const notice = document.getElementById("alert-unavailable");
    if (notice && !notice.hidden) {
      notice.textContent = t("alerts_unavailable");
    }
  });
  renderWatchlist();
  loadNeighborhoods();
  showEmailUnavailable();
})();
