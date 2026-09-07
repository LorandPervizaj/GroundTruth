(function () {
  const t = (key) => window.MetrikI18n.t(key);
  const list = document.getElementById("changelog-list");
  const status = document.getElementById("changelog-status");
  let entries = [];
  let category = "";

  function categoryLabel(value) {
    return t(`changelog_cat_${value}`);
  }

  function render() {
    list.replaceChildren();
    const filtered = category
      ? entries.filter((entry) => entry.category === category)
      : entries;
    status.textContent = filtered.length ? "" : t("changelog_empty");

    for (const entry of filtered) {
      const article = document.createElement("article");
      article.className = "changelog-entry";
      const meta = document.createElement("p");
      meta.className = "hint";
      const date = window.MetrikFormat?.date?.(entry.date) || entry.date;
      meta.textContent = `${date} · ${categoryLabel(entry.category)}`;
      const title = document.createElement("h2");
      title.className = "section-title section-title-sm";
      title.textContent =
        window.MetrikI18n.getLang() === "sq" ? entry.title_sq : entry.title_en;
      const body = document.createElement("p");
      body.textContent =
        window.MetrikI18n.getLang() === "sq" ? entry.body_sq : entry.body_en;
      article.append(meta, title, body);
      list.appendChild(article);
    }
  }

  async function load() {
    try {
      const response = await fetch("/api/changelog");
      if (!response.ok) throw new Error(`Changelog request failed: ${response.status}`);
      entries = (await response.json()).entries || [];
      render();
    } catch {
      status.textContent = t("error_generic");
    }
  }

  document.querySelectorAll("#changelog-filters [data-category]").forEach((button) => {
    button.addEventListener("click", () => {
      category = button.dataset.category;
      document.querySelectorAll("#changelog-filters [data-category]").forEach((item) => {
        item.classList.toggle("active", item === button);
      });
      render();
    });
  });
  document.addEventListener("metrik:langchange", render);
  load();
})();
