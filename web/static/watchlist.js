/** Shared neighborhood watchlist helpers (localStorage). */
(function () {
  const STORAGE_KEY = "metrik_watchlist";
  const t = (k, v) => window.MetrikI18n.t(k, v);

  function load() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    } catch {
      return [];
    }
  }

  function save(items) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  }

  function has(slug) {
    return load().some((item) => item.slug === slug);
  }

  function add(slug, displayName, listingType = "both") {
    const items = load().filter((item) => item.slug !== slug);
    items.push({ slug, display_name: displayName, listing_type: listingType });
    save(items);
  }

  function remove(slug) {
    save(load().filter((item) => item.slug !== slug));
  }

  function toggle(slug, displayName, listingType = "both") {
    if (has(slug)) {
      remove(slug);
      return false;
    }
    add(slug, displayName, listingType);
    return true;
  }

  window.MetrikWatchlist = { load, save, has, add, remove, toggle };
})();
