/**
 * Short-lived in-memory GET cache for Metrik JSON APIs.
 * Dedupes in-flight requests and skips network when a fresh entry exists.
 */
(function (global) {
  const DEFAULT_TTL_MS = 60_000;
  const store = new Map();
  const inflight = new Map();

  function now() {
    return Date.now();
  }

  function getEntry(key) {
    const entry = store.get(key);
    if (!entry) return null;
    if (entry.expiresAt <= now()) {
      store.delete(key);
      return null;
    }
    return entry;
  }

  async function getJson(url, options = {}) {
    const ttlMs = options.ttlMs ?? DEFAULT_TTL_MS;
    const key = options.cacheKey || url;
    const force = Boolean(options.force);
    const fetchInit = options.fetchInit || {};

    if (!force) {
      const hit = getEntry(key);
      if (hit) return hit.data;
      if (inflight.has(key)) return inflight.get(key);
    }

    const pending = (async () => {
      const res = await fetch(url, fetchInit);
      if (!res.ok) {
        const err = new Error(`Request failed: ${res.status}`);
        err.status = res.status;
        err.response = res;
        throw err;
      }
      const data = await res.json();
      store.set(key, { data, expiresAt: now() + ttlMs });
      return data;
    })();

    inflight.set(key, pending);
    try {
      return await pending;
    } finally {
      inflight.delete(key);
    }
  }

  function invalidate(prefix = "") {
    if (!prefix) {
      store.clear();
      return;
    }
    for (const key of store.keys()) {
      if (key.startsWith(prefix)) store.delete(key);
    }
  }

  global.MetrikApiCache = { getJson, invalidate, DEFAULT_TTL_MS };
})(window);
