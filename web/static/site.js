/** Shared navigation, footer, popular markets, language switcher. */
(function () {
  const path = window.location.pathname;
  const t = (k, v) => window.MetrikI18n.t(k, v);

  const POPULAR_MARKETS = [
    { href: "/market/neighborhood/ulpiana", label: "Ulpiana" },
    { href: "/market/neighborhood/arberia", label: "Arbëria" },
    { href: "/market/neighborhood/dardania", label: "Dardania" },
    { href: "/market/neighborhood/matiqan", label: "Matiqan" },
    { href: "/market/district/rruga-b", label: "Rruga B" },
    { href: "/market/complex/royal-mall", label: "Royal Mall" },
  ];

  function renderPopularMarkets() {
    const el = document.getElementById("popular-markets");
    if (!el) return;
    const chips = POPULAR_MARKETS.map(
      (m) => `<a class="market-chip" href="${m.href}">${m.label}</a>`
    ).join("");
    el.innerHTML = `
      <p class="popular-label">${t("popular_markets")}</p>
      <div class="market-chips">${chips}</div>
    `;
  }

  const INSIGHTS_PATHS = ["/statistics", "/compare", "/rent-yield"];
  const TOOLS_PATHS = ["/valuate", "/find"];

  function pathMatchesGroup(paths) {
    return paths.some((p) => path === p || path.startsWith(`${p}/`));
  }

  function navClass(href) {
    if (href === "/" && (path === "/" || path.startsWith("/market"))) return " active";
    if (href === "/statistics" && pathMatchesGroup(INSIGHTS_PATHS)) return " active";
    if (href === "/valuate" && pathMatchesGroup(TOOLS_PATHS)) return " active";
    if (href !== "/" && href !== "/statistics" && href !== "/valuate" && path.startsWith(href)) {
      return " active";
    }
    return "";
  }

  function insightsTabClass(href) {
    const base = href.replace(/\/$/, "");
    if (base === "/statistics" && (path === "/statistics" || path === "/statistics/")) return " active";
    if (base !== "/statistics" && (path === base || path.startsWith(`${base}/`))) return " active";
    return "";
  }

  function toolsTabClass(href) {
    const base = href.replace(/\/$/, "");
    if (path === base || path.startsWith(`${base}/`)) return " active";
    return "";
  }

  function renderInsightsSubnav() {
    const el = document.getElementById("insights-subnav");
    if (!el) return;
    el.innerHTML = `
      <nav class="insights-subnav" aria-label="${t("insights_subnav_label")}">
        <a href="/statistics" class="insights-tab${insightsTabClass("/statistics")}">${t("insights_subnav_annual")}</a>
        <a href="/compare" class="insights-tab${insightsTabClass("/compare")}">${t("insights_subnav_compare")}</a>
        <a href="/rent-yield" class="insights-tab${insightsTabClass("/rent-yield")}">${t("insights_subnav_rent_yield")}</a>
      </nav>
    `;
  }

  function renderToolsSubnav() {
    const el = document.getElementById("tools-subnav");
    if (!el) return;
    el.innerHTML = `
      <nav class="insights-subnav" aria-label="${t("tools_subnav_label")}">
        <a href="/valuate" class="insights-tab${toolsTabClass("/valuate")}">${t("nav_valuate")}</a>
        <a href="/find" class="insights-tab${toolsTabClass("/find")}">${t("nav_find")}</a>
      </nav>
    `;
  }

  function renderLangSwitch() {
    const lang = window.MetrikI18n.getLang();
    return `
      <div class="lang-switch" role="group" aria-label="Language">
        <button type="button" class="lang-btn${lang === "sq" ? " active" : ""}" data-lang="sq">${t("lang_sq")}</button>
        <button type="button" class="lang-btn${lang === "en" ? " active" : ""}" data-lang="en">${t("lang_en")}</button>
      </div>
    `;
  }

  function renderNav() {
    const nav = document.getElementById("site-nav");
    if (!nav) return;
    nav.innerHTML = `
      <nav class="top-nav" aria-label="Main">
        <div class="nav-start">
          <a class="nav-brand" href="/">${t("brand")}</a>
          <div class="nav-links">
            <a href="/" class="nav-link${navClass("/")}">${t("nav_markets")}</a>
            <a href="/valuate" class="nav-link${navClass("/valuate")}">${t("nav_tools")}</a>
            <a href="/statistics" class="nav-link${navClass("/statistics")}">${t("nav_statistics")}</a>
            <a href="/about" class="nav-link${navClass("/about")}">${t("nav_about")}</a>
            <a href="/contact" class="nav-link${navClass("/contact")}">${t("nav_contact")}</a>
          </div>
        </div>
        <button class="nav-toggle" type="button" aria-label="${t("nav_menu")}" aria-expanded="false">☰</button>
        <div class="nav-end">
          ${renderLangSwitch()}
        </div>
      </nav>
    `;
    const toggle = nav.querySelector(".nav-toggle");
    const links = nav.querySelector(".nav-links");
    toggle?.addEventListener("click", () => {
      const open = links?.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    nav.querySelectorAll(".lang-btn").forEach((btn) => {
      btn.addEventListener("click", () => window.MetrikI18n.setLang(btn.dataset.lang));
    });
  }

  function applyCorpusFreshness(meta) {
    if (!meta?.corpus_updated_at) return;
    const date = window.MetrikFormat?.dateTime(meta.corpus_updated_at) || meta.corpus_updated_at;
    const n = window.MetrikFormat?.int(meta.active_listings) || String(meta.active_listings || 0);

    const footerEl = document.getElementById("footer-freshness");
    if (footerEl) {
      footerEl.hidden = false;
      const removed = meta.cross_portal_duplicates_removed || 0;
      footerEl.textContent =
        removed > 0
          ? t("corpus_freshness_deduped", { date, n, raw: meta.raw_listings, removed })
          : t("corpus_freshness_footer", { date, n });
    }

  }

  async function loadCorpusMeta() {
    try {
      const res = await fetch("/api/meta");
      if (!res.ok) return;
      const meta = await res.json();
      window.MetrikCorpusMeta = meta;
      applyCorpusFreshness(meta);
      document.dispatchEvent(new CustomEvent("corpus-meta", { detail: meta }));
    } catch {
      /* offline or API unavailable */
    }
  }

  const COUNT_UP_SELECTOR = ".count-up, .estimate, .pulse-value, .asking-val, .typical-value, .stat-value";

  function animateValue(obj, start, end, duration, originalText) {
    let startTimestamp = null;
    const hasDecimals = originalText.includes('.');
    const hasCommas = originalText.includes(',');
    
    // Extract everything before the first number as prefix, and everything after the last number as suffix
    const match = originalText.match(/^([^0-9.-]*)([0-9.,]+)(.*)$/);
    const prefix = match ? match[1] : '';
    const suffix = match ? match[3] : '';
    
    const step = (timestamp) => {
      if (!startTimestamp) startTimestamp = timestamp;
      const progress = Math.min((timestamp - startTimestamp) / duration, 1);
      const easeProgress = progress * (2 - progress); // easeOut
      const current = easeProgress * (end - start) + start;
      
      const locale = window.MetrikFormat?.locale?.() || "en";
      const forceInteger = originalText.includes("€") || originalText.includes("/m²");
      let displayValue = "";
      if (hasDecimals && !forceInteger) {
         displayValue = hasCommas
           ? current.toLocaleString(locale, { minimumFractionDigits: 1, maximumFractionDigits: 1 })
           : current.toFixed(1);
      } else {
         displayValue = hasCommas
           ? Math.round(current).toLocaleString(locale)
           : Math.round(current).toString();
      }
      
      obj.innerHTML = prefix + displayValue + suffix;
      
      if (progress < 1) {
        window.requestAnimationFrame(step);
      } else {
        obj.innerHTML = originalText;
      }
    };
    window.requestAnimationFrame(step);
  }

  function initCountUp(root) {
    const scope = root && root.querySelectorAll ? root : document;
    const countUpObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          const el = entry.target;
          const text = el.innerText.trim();
          const targetValue = parseFloat(text.replace(/[^0-9.]/g, ""));
          if (!isNaN(targetValue) && targetValue > 0) {
            animateValue(el, 0, targetValue, 1500, text);
          }
          countUpObserver.unobserve(el);
        }
      });
    }, { threshold: 0.1 });

    const nodes = scope === document
      ? document.querySelectorAll(COUNT_UP_SELECTOR)
      : scope.querySelectorAll(COUNT_UP_SELECTOR);
    nodes.forEach((el) => countUpObserver.observe(el));
  }

  function initAnimations() {
    const revealObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-revealed');
          revealObserver.unobserve(entry.target);
        }
      });
    }, { rootMargin: '0px 0px -50px 0px', threshold: 0.1 });

    document.querySelectorAll('.reveal-on-scroll, .panel, .hero, .site-footer').forEach(el => {
      revealObserver.observe(el);
    });

    initCountUp(document);
  }

  function initTabA11y() {
    document.querySelectorAll('[role="tablist"]').forEach((tablist) => {
      if (tablist.dataset.keyboardBound === "true") return;
      const tabs = [...tablist.querySelectorAll('[role="tab"]')];
      if (!tabs.length) return;
      tablist.dataset.keyboardBound = "true";

      const syncTabStops = () => {
        tabs.forEach((tab) => {
          tab.tabIndex = tab.getAttribute("aria-selected") === "true" ? 0 : -1;
        });
      };
      syncTabStops();
      tabs.forEach((tab) => tab.addEventListener("click", syncTabStops));
      tablist.addEventListener("keydown", (event) => {
        const current = tabs.indexOf(document.activeElement);
        if (current < 0) return;
        let next = current;
        if (event.key === "ArrowRight" || event.key === "ArrowDown") {
          next = (current + 1) % tabs.length;
        } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
          next = (current - 1 + tabs.length) % tabs.length;
        } else if (event.key === "Home") {
          next = 0;
        } else if (event.key === "End") {
          next = tabs.length - 1;
        } else {
          return;
        }
        event.preventDefault();
        tabs[next].focus();
        tabs[next].click();
      });
    });
  }

  function ensureInfoTip(el) {
    if (!(el instanceof HTMLElement)) return null;
    el.classList.add("info-tip");
    if (!el.getAttribute("type") && el.tagName === "BUTTON") {
      el.setAttribute("type", "button");
    }
    if (!el.querySelector(".info-tip__icon")) {
      const icon = document.createElement("span");
      icon.className = "info-tip__icon";
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = "i";
      el.appendChild(icon);
    }
    let bubble = el.querySelector(".info-tip__bubble");
    if (!bubble) {
      bubble = document.createElement("span");
      bubble.className = "info-tip__bubble";
      bubble.setAttribute("role", "tooltip");
      el.appendChild(bubble);
    }
    return el;
  }

  function setInfoTipText(el, text) {
    const tip = ensureInfoTip(el);
    if (!tip) return;
    const bubble = tip.querySelector(".info-tip__bubble");
    if (bubble) bubble.textContent = text || "";
    tip.hidden = !text;
    tip.setAttribute("aria-label", window.MetrikI18n?.t?.("info_tip_label") || "Info");
  }

  function refreshInfoTips(root) {
    const scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll(".info-tip[data-i18n-tip]").forEach((el) => {
      const key = el.getAttribute("data-i18n-tip");
      if (!key) return;
      let vars = undefined;
      const rawVars = el.getAttribute("data-i18n-tip-vars");
      if (rawVars) {
        try {
          vars = JSON.parse(rawVars);
        } catch {
          vars = undefined;
        }
      }
      setInfoTipText(el, window.MetrikI18n?.t?.(key, vars) || "");
    });
  }

  function wrapHeadingLabel(heading) {
    if (!(heading instanceof HTMLElement)) return null;
    heading.classList.add("section-title-with-info");
    let label = heading.querySelector(":scope > .section-title-label");
    if (label) return label;
    const tipNodes = [...heading.querySelectorAll(":scope > .info-tip")];
    const badgeNodes = [...heading.querySelectorAll(":scope > .badge, :scope > .score-badge")];
    label = document.createElement("span");
    label.className = "section-title-label";
    if (heading.hasAttribute("data-i18n")) {
      label.setAttribute("data-i18n", heading.getAttribute("data-i18n"));
      heading.removeAttribute("data-i18n");
    }
    const keep = new Set([...tipNodes, ...badgeNodes]);
    while (heading.firstChild) {
      const child = heading.firstChild;
      if (keep.has(child)) break;
      label.appendChild(child);
    }
    heading.insertBefore(label, heading.firstChild);
    tipNodes.forEach((tip) => heading.appendChild(tip));
    badgeNodes.forEach((badge) => heading.appendChild(badge));
    return label;
  }

  function attachInfoTipToHeading(heading, { key, vars, tipId, text } = {}) {
    if (!(heading instanceof HTMLElement)) return null;
    wrapHeadingLabel(heading);
    let tip = heading.querySelector(":scope > .info-tip");
    if (!tip) {
      tip = document.createElement("button");
      tip.type = "button";
      tip.className = "info-tip";
      heading.appendChild(tip);
    }
    if (tipId) tip.id = tipId;
    if (key) {
      tip.setAttribute("data-i18n-tip", key);
      if (vars) tip.setAttribute("data-i18n-tip-vars", JSON.stringify(vars));
      else tip.removeAttribute("data-i18n-tip-vars");
    }
    const resolved =
      text ||
      (key ? window.MetrikI18n?.t?.(key, vars) : "") ||
      "";
    setInfoTipText(tip, resolved);
    return tip;
  }

  function attachInfoTipBeside(target, { key, vars, tipId, text } = {}) {
    if (!(target instanceof HTMLElement)) return null;
    const host = target.parentElement;
    if (!host) return null;
    host.classList.add("section-title-with-info");
    let tip =
      (tipId && document.getElementById(tipId)) ||
      host.querySelector(`:scope > .info-tip[data-i18n-tip="${key || ""}"]`) ||
      null;
    if (!tip) {
      tip = document.createElement("button");
      tip.type = "button";
      tip.className = "info-tip";
      target.insertAdjacentElement("beforebegin", tip);
    }
    if (tipId) tip.id = tipId;
    if (key) {
      tip.setAttribute("data-i18n-tip", key);
      if (vars) tip.setAttribute("data-i18n-tip-vars", JSON.stringify(vars));
      else tip.removeAttribute("data-i18n-tip-vars");
    }
    const resolved =
      text ||
      (key ? window.MetrikI18n?.t?.(key, vars) : "") ||
      "";
    setInfoTipText(tip, resolved);
    return tip;
  }

  function mountInfoTipsFromHints(root) {
    const scope = root && root.querySelectorAll ? root : document;
    scope.querySelectorAll("p.hint.hint-info, .rail-foot.hint-info, .hint.hint-info").forEach((hint) => {
      if (hint.dataset.infoTipMounted === "1") return;
      const attachSel = hint.getAttribute("data-info-attach");
      let target = attachSel ? document.querySelector(attachSel) : hint.previousElementSibling;
      if (!target || !/^(H1|H2|H3|H4|SUMMARY)$/i.test(target.tagName)) {
        if (!attachSel) {
          const parent = hint.closest("section, details, header, .panel, .rail-panel, .statistics-toolbar, form");
          target =
            parent?.querySelector(
              "h1.section-title, h2.section-title, h3.section-title, h4, summary.section-title, .rail-title, h1.hero-title"
            ) || null;
        }
      }
      if (!target) return;
      const key = hint.getAttribute("data-i18n") || hint.getAttribute("data-i18n-tip");
      let vars = undefined;
      const rawVars = hint.getAttribute("data-i18n-tip-vars");
      if (rawVars) {
        try {
          vars = JSON.parse(rawVars);
        } catch {
          vars = undefined;
        }
      }
      const opts = {
        key,
        vars,
        tipId: hint.id ? `${hint.id}-tip` : undefined,
        text: hint.textContent?.trim() || undefined,
      };
      if (/^(H1|H2|H3|H4|SUMMARY)$/i.test(target.tagName) || target.classList.contains("rail-title")) {
        attachInfoTipToHeading(target, opts);
      } else {
        attachInfoTipBeside(target, opts);
      }
      hint.hidden = true;
      hint.setAttribute("aria-hidden", "true");
      hint.dataset.infoTipMounted = "1";
    });
    refreshInfoTips(scope);
  }

  function initInfoTips() {
    mountInfoTipsFromHints(document);
    refreshInfoTips(document);
    document.querySelectorAll(".info-tip").forEach((tip) => {
      if (tip.dataset.infoTipBound) return;
      tip.dataset.infoTipBound = "1";
      tip.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
      });
    });
  }

  function renderAll() {
    renderNav();
    renderInsightsSubnav();
    renderToolsSubnav();
    renderPopularMarkets();
    window.MetrikI18n.apply();
    initInfoTips();
    initTabA11y();
    loadCorpusMeta();
    setTimeout(initAnimations, 100);
  }

  window.MetrikSite = {
    applyCorpusFreshness,
    loadCorpusMeta,
    initCountUp,
    ensureInfoTip,
    setInfoTipText,
    refreshInfoTips,
    initInfoTips,
  };

  function visitorId() {
    try {
      let id = localStorage.getItem("metrik_vid");
      if (!id) {
        id = (crypto.randomUUID && crypto.randomUUID()) || `v-${Date.now()}`;
        localStorage.setItem("metrik_vid", id);
      }
      return id;
    } catch {
      return null;
    }
  }

  window.MetrikTrack = {
    visitorId,
    track(event, extra = {}) {
      fetch("/api/events", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Visitor-Id": visitorId() || "",
        },
        body: JSON.stringify({
          event,
          visitor_id: visitorId(),
          municipality: "Prishtina",
          ...extra,
        }),
      }).catch(() => {});
    },
  };

  window.MetrikSearchA11y = {
    bind(input, listEl) {
      if (!input || !listEl) return null;
      if (!listEl.id) listEl.id = `search-list-${Math.random().toString(36).slice(2, 8)}`;
      input.setAttribute("role", "combobox");
      input.setAttribute("aria-autocomplete", "list");
      input.setAttribute("aria-expanded", "false");
      input.setAttribute("aria-controls", listEl.id);
      return {
        setOpen(open) {
          input.setAttribute("aria-expanded", open ? "true" : "false");
        },
      };
    },
  };
  document.addEventListener("metrik:langchange", () => {
    if (window.MetrikCorpusMeta) applyCorpusFreshness(window.MetrikCorpusMeta);
  });

  renderAll();
  document.addEventListener("metrik:langchange", renderAll);
})();
