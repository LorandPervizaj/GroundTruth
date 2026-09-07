/**
 * Shared market entity search (home hero + market toolbar).
 */
(function () {
  const t = (k, v) => window.MetrikI18n.t(k, v);
  let resultId = 0;

  const ENTITY_KEYS = {
    neighborhood: "search_entity_neighborhood",
    district: "search_entity_district",
    street: "search_entity_street",
    complex: "search_entity_complex",
  };

  function entityLabel(type) {
    const key = ENTITY_KEYS[type];
    return key ? t(key) : type;
  }

  function marketPath(entityType, slug) {
    return `/market/${entityType}/${slug}`;
  }

  function track(event, extra = {}) {
    if (window.MetrikTrack) {
      window.MetrikTrack.track(event, extra);
      return;
    }
    fetch("/api/events", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event, municipality: "Prishtina", ...extra }),
    }).catch(() => {});
  }

  function buildResultItem(item, { onSelect, query, section }) {
    const li = document.createElement("li");
    li.className = "metrik-search-item combo-item";
    li.role = "option";
    li.tabIndex = -1;
    li.id = `metrik-search-option-${++resultId}`;

    const listings =
      item.listings != null
        ? `${item.listings} ${t("listings")}`
        : "";
    const meta = [item.subtitle, listings].filter(Boolean).join(" · ");

    const head = document.createElement("div");
    head.className = "metrik-search-item-head";
    const entity = document.createElement("span");
    entity.className = "metrik-search-entity";
    entity.textContent = entityLabel(item.entity_type);
    const name = document.createElement("strong");
    name.className = "metrik-search-name";
    name.textContent = item.display_name;
    head.append(entity, name);
    li.appendChild(head);
    if (meta) {
      const detail = document.createElement("span");
      detail.className = "metrik-search-meta";
      detail.textContent = meta;
      li.appendChild(detail);
    }

    li.addEventListener("mousedown", (e) => {
      e.preventDefault();
      track("market_search_select", {
        query,
        entity_type: item.entity_type,
        slug: item.slug,
        section,
      });
      onSelect(item);
    });
    return li;
  }

  function setActiveItem(list, index, input = null) {
    const items = [...list.querySelectorAll(".metrik-search-item")];
    items.forEach((el, i) => {
      const active = i === index;
      el.classList.toggle("metrik-search-item-active", active);
      el.setAttribute("aria-selected", active ? "true" : "false");
      if (active) el.scrollIntoView({ block: "nearest" });
    });
    const active = items[index] || null;
    if (input) {
      if (active) input.setAttribute("aria-activedescendant", active.id);
      else input.removeAttribute("aria-activedescendant");
    }
    return active;
  }

  function init(opts) {
    const {
      input,
      list,
      hint = null,
      root = null,
      minChars = 2,
      section = "search",
      debounceMs = 200,
      onSelect = (item) => {
        window.location.href = marketPath(item.entity_type, item.slug);
      },
    } = opts;

    if (!input || !list) return null;

    const shell = root || input.closest(".metrik-search") || input.parentElement;
    const searchA11y = window.MetrikSearchA11y?.bind(input, list);
    let timer = null;
    let activeIndex = -1;
    let lastQuery = "";

    function close() {
      list.classList.add("hidden");
      searchA11y?.setOpen(false);
      activeIndex = -1;
      setActiveItem(list, -1, input);
    }

    function open() {
      list.classList.remove("hidden");
      searchA11y?.setOpen(true);
    }

    function setHint(text) {
      if (hint) hint.textContent = text;
    }

    function renderResults(items, query) {
      list.innerHTML = "";
      activeIndex = -1;

      if (!items.length) {
        close();
        setHint(t("search_no_match"));
        track("zero_results", { query_length: query.length, section });
        return;
      }

      const label = items.length === 1 ? t("result") : t("results");
      setHint(`${items.length} ${label}`);
      open();

      for (const item of items) {
        list.appendChild(
          buildResultItem(item, { onSelect, query, section })
        );
      }
    }

    async function runSearch(query) {
      lastQuery = query;
      if (query.length < minChars) {
        close();
        setHint(query.length === 0 ? "" : t("search_hint_min"));
        return;
      }
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        if (!res.ok) return;
        const data = await res.json();
        renderResults(data.results || [], query);
        track("search_performed", {
          query_length: query.length,
          results_count: (data.results || []).length,
          section,
        });
        if (section === "market") track("market_search", { query });
      } catch {
        setHint(t("search_unavailable"));
        close();
      }
    }

    input.addEventListener("input", () => {
      clearTimeout(timer);
      const q = input.value.trim();
      timer = setTimeout(() => runSearch(q), debounceMs);
    });

    input.addEventListener("keydown", (e) => {
      const items = [...list.querySelectorAll(".metrik-search-item")];
      if (!items.length || list.classList.contains("hidden")) {
        if (e.key === "Enter") e.preventDefault();
        return;
      }

      if (e.key === "ArrowDown") {
        e.preventDefault();
        activeIndex = Math.min(activeIndex + 1, items.length - 1);
        setActiveItem(list, activeIndex, input);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        activeIndex = Math.max(activeIndex - 1, 0);
        setActiveItem(list, activeIndex, input);
      } else if (e.key === "Escape") {
        close();
        input.blur();
      } else if (e.key === "Enter") {
        e.preventDefault();
        const pick = items[activeIndex >= 0 ? activeIndex : 0];
        if (pick) pick.dispatchEvent(new MouseEvent("mousedown"));
      }
    });

    document.addEventListener("click", (e) => {
      if (!shell?.contains(e.target)) close();
    });

    return { close, runSearch };
  }

  window.MetrikSearch = { init, buildResultItem, entityLabel, marketPath };
})();
