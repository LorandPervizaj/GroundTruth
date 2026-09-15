/** Annual market report, charts + bilingual narratives from API. */
(function () {
  const t = (k, v) => window.MetrikI18n.t(k, v);
  let reportData = null;
  let lastDataRevision = null;
  const POLL_MS = 60_000;

  function lang() {
    return window.MetrikI18n.getLang();
  }

  function pickI18n(obj) {
    if (!obj) return null;
    return obj[lang()] || obj.sq || null;
  }

  function narrativesFor(data) {
    const i18n = data.narratives_i18n || {};
    return i18n[lang()] || data.narratives || {};
  }

  function insightsFor(data) {
    const c = data.insights || data.conclusions || {};
    return c[lang()] || c.sq || [];
  }

  function executiveSummaryFor(data) {
    const s = data.executive_summary || {};
    return s[lang()] || s.sq || t("annual_summary_empty");
  }

  const fmt = () => window.MetrikFormat;
  const esc = (v) => window.MetrikSanitize.escapeHtml(v);
  const seg = (v) => window.MetrikSanitize.pathSegment(v);
  const fmtNum = (n) => fmt().int(n);
  const fmtEuroSale = (n) => fmt().euroSale(n);
  const fmtSalePsm = (n) => (n == null ? "-" : fmt().euroSalePsm(n));
  const fmtRent = (n) => (n == null ? "-" : `${fmt().euroRent(n)}${t("per_month_suffix")}`);
  const fmtPct = (n) => fmt().percent(n);

  let chartLoader = null;
  function ensureChartJs() {
    if (window.Chart) return Promise.resolve();
    if (chartLoader) return chartLoader;
    chartLoader = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "/static/chart.umd.min.js?v=4.4.8";
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("Chart.js failed to load"));
      document.head.appendChild(script);
    });
    return chartLoader;
  }

  function renderDisclaimer() {
    const el = document.getElementById("annual-disclaimer");
    if (el) el.textContent = t("annual_disclaimer");
  }

  function sampleBadge(sample) {
    if (!sample?.confidence || !window.MetrikConfidence) return "";
    return window.MetrikConfidence.badge(sample, { levelOnly: true });
  }

  function renderKpis(data) {
    const grid = document.getElementById("annual-kpis");
    if (!grid) return;
    const k = data.kpis || {};
    const cards = [
      { label: t("annual_kpi_total"), value: fmtNum(k.total_listings), sample: k.total_sample },
      { label: t("annual_kpi_rent_share"), value: fmtPct(k.rent_pct), sample: k.rent_sample },
      {
        label: t("annual_kpi_median_psm"),
        value: fmtSalePsm(k.median_sale_price_per_sqm),
        sample: k.median_sale_sample || k.sale_sample,
      },
      {
        label: t("annual_kpi_median_rent"),
        value: fmtRent(k.median_rent),
        sample: k.median_rent_sample || k.rent_sample,
      },
    ];
    grid.innerHTML = cards
      .map(
        (c) => `
        <div class="pulse-card">
          <span class="pulse-label">${esc(c.label)}</span>
          <span class="pulse-value">${esc(c.value)}</span>
        </div>`
      )
      .join("");
  }

  function renderSummaryStrip(data) {
    const el = document.getElementById("annual-summary-strip");
    if (!el) return;
    el.textContent = executiveSummaryFor(data);
  }

  function renderHero() {
    const lead = document.getElementById("annual-hero-lead");
    if (lead) lead.textContent = t("statistics_hero_lead");
  }

  function renderConclusions(data) {
    const list = document.getElementById("conclusions-list");
    if (!list) return;
    list.innerHTML = "";
    for (const line of insightsFor(data)) {
      const li = document.createElement("li");
      li.textContent = line;
      list.appendChild(li);
    }
  }

  function renderQuality(data) {
    const cov = data.coverage_narrative || {};
    const label = pickI18n(cov.label);
    const summary = pickI18n(cov.summary);
    const items = pickI18n(cov.items) || [];

    const scoreEl = document.getElementById("confidence-score");
    if (scoreEl) scoreEl.textContent = label || "-";

    const textEl = document.getElementById("confidence-text");
    if (textEl) textEl.textContent = summary || "";

    const listEl = document.getElementById("coverage-list");
    if (listEl) {
      listEl.innerHTML = "";
      for (const line of items) {
        const li = document.createElement("li");
        li.textContent = line;
        listEl.appendChild(li);
      }
    }
  }

  function renderNarratives(data) {
    const n = narrativesFor(data);
    const map = [
      ["volume-insight", "volume_insight"],
      ["price-insight", "price_insight"],
      ["rent-insight", "rent_insight"],
      ["nh-insight", "nh_insight"],
    ];
    for (const [id, key] of map) {
      const el = document.getElementById(id);
      if (el && n[key]) el.textContent = n[key];
    }
  }

  function chartFontSize(token, fallback) {
    const raw = getComputedStyle(document.documentElement).getPropertyValue(token).trim();
    const px = parseFloat(raw);
    return Number.isFinite(px) && px > 0 ? px : fallback;
  }

  function chartOptions() {
    const theme = window.MetrikTheme?.chartTheme?.() || {};
    const label = theme.label || "#333";
    const tick = theme.tick || "#6b6b6b";
    const grid = theme.grid || "#e5e5e0";
    const legendSize = chartFontSize("--chart-font", 13);
    const tickSize = chartFontSize("--chart-font-sm", 11);
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "top",
          labels: { font: { family: "inherit", size: legendSize }, color: label },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          grid: { color: grid },
          ticks: { font: { family: "inherit", size: tickSize }, color: tick },
        },
        x: {
          grid: { display: false },
          ticks: { font: { family: "inherit", size: tickSize }, color: tick },
        },
      },
    };
  }

  let volumeChart;
  let priceChart;
  let rentChart;
  let nhChart;

  function outlierPointStyles(labels, exclusions) {
    const theme = window.MetrikTheme?.chartTheme?.() || {};
    const primary = theme.primary || "#1a4d38";
    const outlier = theme.outlier || "#c45c26";
    const excluded = new Set((exclusions || []).map((e) => e.month));
    return labels.map((label) => (excluded.has(label) ? outlier : primary));
  }

  function outlierRadius(labels, exclusions) {
    const excluded = new Set((exclusions || []).map((e) => e.month));
    return labels.map((label) => (excluded.has(label) ? 7 : 4));
  }

  function appendOutlierNote(containerId, exclusions) {
    if (!exclusions?.length) return;
    const el = document.getElementById(containerId);
    if (!el) return;
    const note = document.createElement("p");
    note.className = "chart-outlier-note hint";
    note.textContent = t("chart_outlier_note");
    el.parentElement?.appendChild(note);
  }

  function renderCharts(data) {
    if (typeof window.Chart !== "function") {
      throw new Error("Chart.js is unavailable");
    }
    const opts = chartOptions();
    const theme = window.MetrikTheme?.chartTheme?.() || {};
    const primary = theme.primary || "#1a4d38";
    const secondary = theme.secondary || "#8bb9a3";
    const tertiary = theme.tertiary || "#5a7a6a";
    const primaryFill = theme.primaryFill || "rgba(26, 77, 56, 0.05)";
    const tertiaryFill = theme.tertiaryFill || "rgba(90, 122, 106, 0.08)";
    const grid = theme.grid || "#e5e5e0";
    const tick = theme.tick || "#6b6b6b";
    const label = theme.label || "#333";
    const pointBorder = theme.pointBorder || "#fff";
    setChartNote(
      "volume-chart-note",
      chartSampleNote(
        (data.volume?.sale || []).map((n, i) => n + (data.volume?.rent?.[i] || 0))
      )
    );

    const volCtx = document.getElementById("volumeChart");
    if (volCtx) {
      if (volumeChart) volumeChart.destroy();
      const datasets = [
        {
          label: t("annual_chart_sale"),
          data: data.volume.sale,
          backgroundColor: primary,
          borderRadius: 4,
        },
        {
          label: t("annual_chart_rent"),
          data: data.volume.rent,
          backgroundColor: secondary,
          borderRadius: 4,
        },
      ];
      volumeChart = new Chart(volCtx, {
        type: "bar",
        data: {
          labels: data.volume.labels,
          datasets,
        },
        options: opts,
      });
    }

    setChartNote("price-chart-note", chartSampleNote(data.prices?.counts));

    const priceCtx = document.getElementById("priceChart");
    if (priceCtx) {
      if (priceChart) priceChart.destroy();
      const priceLabels = data.prices.labels;
      const priceExcl = data.prices.excluded_months || [];
      priceChart = new Chart(priceCtx, {
        type: "line",
        data: {
          labels: priceLabels,
          datasets: [
            {
              label: t("annual_chart_median_psm"),
              data: data.prices.values,
              spanGaps: true,
              borderColor: primary,
              backgroundColor: primaryFill,
              borderWidth: 2.5,
              fill: true,
              tension: 0.25,
              pointBackgroundColor: outlierPointStyles(priceLabels, priceExcl),
              pointBorderColor: pointBorder,
              pointBorderWidth: 2,
              pointRadius: outlierRadius(priceLabels, priceExcl),
              pointHoverRadius: 6,
            },
          ],
        },
        options: opts,
      });
      appendOutlierNote("price-chart-note", priceExcl);
    }

    setChartNote("rent-chart-note", chartSampleNote(data.rent_prices?.counts));

    const rentCtx = document.getElementById("rentChart");
    if (rentCtx && data.rent_prices) {
      if (rentChart) rentChart.destroy();
      const rentLabels = data.rent_prices.labels;
      const rentExcl = data.rent_prices.excluded_months || [];
      rentChart = new Chart(rentCtx, {
        type: "line",
        data: {
          labels: rentLabels,
          datasets: [
            {
              label: t("annual_chart_median_rent"),
              data: data.rent_prices.values,
              spanGaps: true,
              borderColor: tertiary,
              backgroundColor: tertiaryFill,
              borderWidth: 2.5,
              fill: true,
              tension: 0.25,
              pointBackgroundColor: outlierPointStyles(rentLabels, rentExcl),
              pointBorderColor: pointBorder,
              pointBorderWidth: 2,
              pointRadius: outlierRadius(rentLabels, rentExcl),
              pointHoverRadius: 6,
            },
          ],
        },
        options: opts,
      });
      appendOutlierNote("rent-chart-note", rentExcl);
    }

    const nhCtx = document.getElementById("nhChart");
    if (nhCtx) {
      if (nhChart) nhChart.destroy();
      const rankingRows = [
        ...(data.neighborhood_rankings?.expensive || []),
      ]
        .filter((r) => r.median_price_per_sqm != null)
        .slice(0, 8);
      const fallbackRows = (data.neighborhood_table || data.neighborhood_highlights || [])
        .filter((r) => r.median_price_per_sqm != null)
        .sort((a, b) => Number(b.median_price_per_sqm) - Number(a.median_price_per_sqm))
        .slice(0, 8);
      const rows = rankingRows.length ? rankingRows : fallbackRows;
      if (rows.length) {
        nhChart = new Chart(nhCtx, {
          type: "bar",
          data: {
            labels: rows.map((n) => n.neighborhood || n.name),
            datasets: [
              {
                label: t("annual_chart_median_psm"),
                data: rows.map((n) => n.median_price_per_sqm),
                backgroundColor: primary,
                borderRadius: 4,
              },
            ],
          },
          options: {
            ...opts,
            indexAxis: "y",
            scales: {
              x: {
                beginAtZero: false,
                grid: { color: grid },
                ticks: { font: { family: "inherit", size: chartFontSize("--chart-font-sm", 11) }, color: tick },
              },
              y: {
                grid: { display: false },
                ticks: { font: { family: "inherit", size: chartFontSize("--chart-font", 13), weight: "500" }, color: label },
              },
            },
          },
        });
      }
    }

    renderRankingCharts(data);
    renderSegmentCharts(data);
  }

  function renderRankingCharts(data) {
    const charts = window.MetrikCharts;
    const rankings = data.neighborhood_rankings;
    if (!charts || !rankings) return;

    function paint(canvasId, rows, chartRefName) {
      const canvas = document.getElementById(canvasId);
      if (!canvas) return;
      const list = (rows || []).filter((r) => r.median_price_per_sqm != null);
      if (!list.length) {
        charts.destroy(canvas);
        return;
      }
      charts.createHorizontalBarChart(canvas, {
        labels: list.map((r) => r.neighborhood),
        values: list.map((r) => r.median_price_per_sqm),
        label: t("annual_chart_median_psm"),
        formatTick: (v) => fmtSalePsm(v),
        tooltipBuilder: (items) => {
          const idx = items[0]?.dataIndex ?? 0;
          const row = list[idx];
          if (!row) return { title: "", lines: [] };
          return {
            title: row.neighborhood,
            lines: [
              `${t("annual_nh_col_psm")}: ${fmtSalePsm(row.median_price_per_sqm)}`,
              `${t("annual_nh_col_median_sale")}: ${fmtEuroSale(row.median_sale_eur)}`,
              t("chart_tooltip_n", { n: row.n ?? "—" }),
              t("chart_tooltip_confidence", {
                level: window.MetrikI18n.translateConfidence(row.confidence || "insufficient"),
              }),
            ],
          };
        },
      });
    }

    paint("expensiveNhChart", rankings.expensive);
    paint("affordableNhChart", rankings.affordable);
  }

  function renderSegmentCharts(data) {
    const charts = window.MetrikCharts;
    const seg = data.apartment_segments || {};
    if (!charts) return;

    function paint(canvasId, rows) {
      const canvas = document.getElementById(canvasId);
      if (!canvas) return;
      const list = (rows || []).filter((r) => r.median_sale_psm != null);
      if (!list.length) {
        charts.destroy(canvas);
        return;
      }
      charts.createHorizontalBarChart(canvas, {
        labels: list.map((r) => formatSegmentLabel(r.segment)),
        values: list.map((r) => r.median_sale_psm),
        label: t("annual_chart_median_psm"),
        formatTick: (v) => fmtSalePsm(v),
        tooltipBuilder: (items) => {
          const idx = items[0]?.dataIndex ?? 0;
          const row = list[idx];
          if (!row) return { title: "", lines: [] };
          return {
            title: formatSegmentLabel(row.segment),
            lines: [
              `${t("annual_nh_col_psm")}: ${fmtSalePsm(row.median_sale_psm)}`,
              `${t("listings")}: ${fmtNum(row.listings)}`,
              `${t("annual_nh_col_rent")}: ${fmtRent(row.median_rent)}`,
            ],
          };
        },
      });
    }

    paint("bedroomSegmentChart", sortSegmentRows(seg.by_bedrooms, BEDROOM_SEGMENT_ORDER));
    paint("sizeSegmentChart", sortSegmentRows(seg.by_size_band, SIZE_BAND_ORDER));
  }

  function nhLinkCell(row) {
    const td = document.createElement("td");
    if (row.slug) {
      const a = document.createElement("a");
      a.href = `/market/neighborhood/${seg(row.slug)}`;
      a.textContent = row.neighborhood;
      td.appendChild(a);
    } else {
      td.textContent = row.neighborhood;
    }
    return td;
  }

  function renderRankingTable(bodyId, rows) {
    const body = document.getElementById(bodyId);
    if (!body) return;
    body.innerHTML = "";
    for (const row of rows) {
      const tr = document.createElement("tr");
      tr.className = window.MetrikConfidence?.rowClass({
        confidence: row.confidence,
        n: row.n,
      }) || "";
      tr.appendChild(nhLinkCell(row));
      const psm = document.createElement("td");
      psm.textContent = fmtSalePsm(row.median_price_per_sqm);
      tr.appendChild(psm);
      const sale = document.createElement("td");
      sale.textContent = fmtEuroSale(row.median_sale_eur);
      tr.appendChild(sale);
      const conf = document.createElement("td");
      conf.innerHTML = sampleBadge({ n: row.n, confidence: row.confidence });
      tr.appendChild(conf);
      body.appendChild(tr);
    }
  }

  function renderNeighborhoodRankings(data) {
    const section = document.getElementById("annual-rankings-section");
    const rankings = data.neighborhood_rankings;
    if (!section || !rankings) return;
    const hasRows = rankings.expensive?.length || rankings.affordable?.length;
    section.hidden = !hasRows;
    if (!hasRows) return;
    const hint = document.getElementById("annual-rankings-hint");
    const n = rankings.min_sale_listings || 15;
    const text = t("annual_rankings_hint", { n });
    if (hint) {
      hint.classList.add("hint-info");
      hint.setAttribute("data-i18n-tip", "annual_rankings_hint");
      hint.setAttribute("data-i18n-tip-vars", JSON.stringify({ n }));
      hint.textContent = text;
    }
    const title = section.querySelector(".section-title");
    let tip = document.getElementById("annual-rankings-hint-tip") || title?.querySelector(".info-tip");
    if (!tip && hint) {
      delete hint.dataset.infoTipMounted;
      window.MetrikSite?.initInfoTips?.();
      tip = document.getElementById("annual-rankings-hint-tip") || title?.querySelector(".info-tip");
    }
    if (tip) {
      tip.setAttribute("data-i18n-tip", "annual_rankings_hint");
      tip.setAttribute("data-i18n-tip-vars", JSON.stringify({ n }));
      window.MetrikSite?.setInfoTipText?.(tip, text);
    }
    renderRankingTable("expensive-nh-body", rankings.expensive || []);
    renderRankingTable("affordable-nh-body", rankings.affordable || []);
  }

  function renderNeighborhoodTable(data) {
    const body = document.getElementById("nh-table-body");
    if (!body) return;
    const rows = data.neighborhood_table || data.neighborhood_highlights || [];
    body.innerHTML = "";
    for (const row of rows) {
      const tr = document.createElement("tr");
      tr.appendChild(nhLinkCell(row));
      const inv = document.createElement("td");
      inv.textContent = fmtNum(row.inventory);
      tr.appendChild(inv);
      const psm = document.createElement("td");
      psm.textContent = fmtSalePsm(row.median_price_per_sqm);
      tr.appendChild(psm);
      const rent = document.createElement("td");
      rent.textContent = fmtRent(row.median_rent);
      tr.appendChild(rent);
      body.appendChild(tr);
    }
  }

  const BEDROOM_SEGMENT_ORDER = ["0 BR", "1 BR", "2 BR", "3 BR", "4+ BR"];
  const SIZE_BAND_ORDER = ["<50m²", "50-79m²", "80-109m²", "110m²+"];

  function formatSegmentLabel(segment) {
    if (segment == null || segment === "") return "-";
    const label = String(segment);
    const lang = window.MetrikI18n?.getLang?.() || "sq";
    if (lang === "sq" && /\bBR\b/.test(label)) {
      return label.replace(/\bBR\b/g, "Dhoma");
    }
    return label;
  }

  function sortSegmentRows(rows, order) {
    const rank = Object.fromEntries(order.map((key, i) => [key, i]));
    return [...(rows || [])].sort((a, b) => {
      const left = rank[a?.segment] ?? order.length;
      const right = rank[b?.segment] ?? order.length;
      if (left !== right) return left - right;
      return String(a?.segment || "").localeCompare(String(b?.segment || ""));
    });
  }

  function renderApartmentSegments(data) {
    const seg = data.apartment_segments || {};
    const bedroomRows = sortSegmentRows(seg.by_bedrooms || [], BEDROOM_SEGMENT_ORDER);
    const sizeRows = sortSegmentRows(seg.by_size_band || [], SIZE_BAND_ORDER);

    const renderRows = (bodyId, rows) => {
      const body = document.getElementById(bodyId);
      if (!body) return;
      body.innerHTML = "";
      for (const row of rows) {
        const tr = document.createElement("tr");
        const name = document.createElement("td");
        name.textContent = formatSegmentLabel(row.segment);
        tr.appendChild(name);
        const n = document.createElement("td");
        n.textContent = fmtNum(row.listings || 0);
        tr.appendChild(n);
        const psm = document.createElement("td");
        psm.textContent = fmtSalePsm(row.median_sale_psm);
        tr.appendChild(psm);
        const sale = document.createElement("td");
        sale.textContent = fmtEuroSale(row.median_sale_price);
        tr.appendChild(sale);
        const rent = document.createElement("td");
        rent.textContent = fmtRent(row.median_rent);
        tr.appendChild(rent);
        body.appendChild(tr);
      }
    };

    renderRows("segments-bedroom-body", bedroomRows);
    renderRows("segments-size-body", sizeRows);

    const recoList = document.getElementById("segments-reco-list");
    if (!recoList) return;
    recoList.innerHTML = "";
    const r = seg.recommendations || data.market_insights?.segment_recommendations || {};
    const lines = [
      t("annual_reco_buy", { segment: formatSegmentLabel(r.best_buy_value?.segment) }),
      t("annual_reco_buy_to_rent", {
        segment: formatSegmentLabel(r.best_buy_to_rent?.segment),
        yield: r.best_buy_to_rent?.yield_pct != null ? `${r.best_buy_to_rent.yield_pct}%` : "-",
      }),
      t("annual_reco_rent", { segment: formatSegmentLabel(r.best_rent_value?.segment) }),
    ];
    for (const line of lines) {
      const li = document.createElement("li");
      li.textContent = line;
      recoList.appendChild(li);
    }
  }

  function propertyTypeLabel(code) {
    if (!code) return "-";
    const key = `annual_property_type_${String(code).toLowerCase()}`;
    const label = t(key);
    return label !== key ? label : String(code);
  }

  function renderSimpleNhTable(bodyId, rows, columns) {
    const body = document.getElementById(bodyId);
    if (!body) return;
    body.innerHTML = "";
    for (const row of rows) {
      const tr = document.createElement("tr");
      for (const col of columns) {
        const td = document.createElement("td");
        if (col === "neighborhood") {
          tr.appendChild(nhLinkCell(row));
          continue;
        }
        const val = row[col];
        if (col === "top_property_type") td.textContent = propertyTypeLabel(val);
        else if (col === "top_bedroom_segment") td.textContent = formatSegmentLabel(val);
        else if (col === "gross_yield_pct") td.textContent = val != null ? fmtPct(val) : "-";
        else if (col === "median_price_per_sqm") td.textContent = fmtSalePsm(val);
        else if (col === "median_sale_eur") td.textContent = fmtEuroSale(val);
        else if (col === "median_rent_eur") td.textContent = fmtRent(val);
        else if (col === "top_property_type_pct") td.textContent = val != null ? `${val}%` : "-";
        else td.textContent = val != null && val !== "" ? String(val) : "-";
        tr.appendChild(td);
      }
      body.appendChild(tr);
    }
  }

  function renderMarketInsights(data) {
    const insights = data.market_insights || {};
    const section = document.getElementById("annual-insights-section");
    if (!section) return;

    const city = insights.property_types?.city || {};
    const common = insights.common_segments || {};
    const callouts = document.getElementById("insights-callouts");
    if (callouts) {
      const lines = [];
      if (city.top_type) {
        lines.push(
          t("annual_insights_top_type_city", {
            type: propertyTypeLabel(city.top_type),
            pct: city.top_pct ?? "-",
          })
        );
      }
      if (common.most_common_bedroom?.segment) {
        lines.push(
          t("annual_insights_most_common_br", {
            segment: formatSegmentLabel(common.most_common_bedroom.segment),
            n: fmtNum(common.most_common_bedroom.listings),
          })
        );
      }
      if (common.most_common_size_band?.segment) {
        lines.push(
          t("annual_insights_most_common_size", {
            segment: formatSegmentLabel(common.most_common_size_band.segment),
            n: fmtNum(common.most_common_size_band.listings),
          })
        );
      }
      if (common.most_expensive_bedroom?.segment) {
        lines.push(
          t("annual_insights_expensive_br", {
            segment: formatSegmentLabel(common.most_expensive_bedroom.segment),
            psm: fmtSalePsm(common.most_expensive_bedroom.median_sale_psm),
          })
        );
      }
      if (common.most_expensive_size_band?.segment) {
        lines.push(
          t("annual_insights_expensive_size", {
            segment: formatSegmentLabel(common.most_expensive_size_band.segment),
            psm: fmtSalePsm(common.most_expensive_size_band.median_sale_psm),
          })
        );
      }
      callouts.innerHTML = lines.map((line) => `<p class="hint hint-flush">${esc(line)}</p>`).join("");
    }

    const topTypeEl = document.getElementById("insights-top-type-city");
    if (topTypeEl && city.types?.length) {
      topTypeEl.textContent = city.types
        .map((row) => `${propertyTypeLabel(row.type)} ${row.pct}%`)
        .join(" · ");
    }

    renderSimpleNhTable(
      "property-type-nh-body",
      (insights.property_types?.by_neighborhood || []).map((row) => ({
        ...row,
        top_property_type: `${propertyTypeLabel(row.top_property_type)} (${row.top_property_type_pct}%)`,
      })),
      ["neighborhood", "top_property_type", "listings"]
    );

    renderApartmentSegments(data);

    renderSimpleNhTable(
      "nh-profiles-body",
      insights.neighborhood_profiles || [],
      ["neighborhood", "top_bedroom_segment", "top_size_band", "listings"]
    );

    renderSimpleNhTable(
      "best-yield-body",
      insights.best_rent_yield || [],
      ["neighborhood", "gross_yield_pct", "median_rent_eur", "median_sale_eur"]
    );

    renderSimpleNhTable(
      "best-live-body",
      insights.best_to_live || [],
      ["neighborhood", "median_price_per_sqm", "median_sale_eur"]
    );
  }

  function chartSampleNote(counts) {
    if (!counts?.length) return "";
    const max = Math.max(...counts);
    const min = Math.min(...counts);
    return t("chart_sample_range", { min: fmtNum(min), max: fmtNum(max) });
  }

  function setChartNote(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text || "";
  }

  function renderFormulas(data) {
    const list = document.getElementById("formula-list");
    if (!list) return;
    const formulas = data.formulas || [];
    list.innerHTML = "";
    for (const item of formulas) {
      const li = document.createElement("li");
      li.className = "formula-item";
      const label = pickI18n(item.label) || item.id;
      const expr = pickI18n(item.formula) || "";
      const used = (item.used_in || []).join(", ");
      li.innerHTML = `
        <span class="formula-label">${esc(label)}</span>
        <code class="formula-expr">${esc(expr)}</code>
        <span class="formula-used">${esc(t("annual_formulas_used_in", { sections: used }))}</span>`;
      list.appendChild(li);
    }
  }

  function renderRefreshNote(data) {
    const badge = document.getElementById("annual-freshness-badge");
    if (!badge) return;
    const when = data.generated_at;
    if (!when) {
      badge.hidden = true;
      return;
    }
    badge.hidden = false;
    badge.textContent = t("data_updated_at", {
      date: fmt().dateTime(when),
    });
  }

  function renderMethodology(data) {
    const el = document.getElementById("methodology-text");
    if (!el) return;

    const plain = pickI18n(data.methodology_plain?.plain);
    if (plain) {
      el.textContent = plain;
    } else if (data.methodology) {
      const m = data.methodology;
      el.textContent = t("annual_methodology_fallback", {
        months: m.window_months,
        cutoff: m.cutoff_date,
      });
    }

    const techEl = document.getElementById("methodology-technical");
    if (techEl) {
      const tech = data.methodology_plain?.technical || {};
      const m = data.methodology || {};
      const parts = [];
      // Never list raw parser version strings publicly (they can embed portal tokens).
      if (tech.parsers || m.parser_versions?.length) {
        const count = m.parser_versions?.length
          ? m.parser_versions.length
          : null;
        parts.push(
          count
            ? t("methodology_parsers_note_vague")
            : t("annual_methodology_parsers", { v: String(tech.parsers || "") })
        );
      }
      if (tech.gazetteer || m.gazetteer_version) {
        parts.push(t("annual_methodology_gazetteer", { v: tech.gazetteer || m.gazetteer_version }));
      }
      const generated = tech.generated || (data.generated_at ? data.generated_at.slice(0, 10) : null);
      if (generated) {
        parts.push(t("annual_methodology_generated", { date: generated }));
      }
      techEl.textContent = parts.join(" ");
      techEl.hidden = !parts.length;
    }

    const genEl = document.getElementById("annual-generated-at");
    if (genEl) genEl.hidden = true;
  }

  function renderPdfButtons() {
    const url = `/api/reports/annual_pdf?lang=${lang()}`;
    document.querySelectorAll(".pdf-download-btn").forEach((btn) => {
      btn.href = url;
      btn.onclick = () => {
        window.MetrikTrack?.track("report_downloaded", {
          report_type: "annual_pdf",
          section: lang(),
          municipality: "Prishtina",
        });
      };
    });
  }

  async function renderAll({ animateCounts = false } = {}) {
    if (!reportData) return;
    renderPdfButtons();
    renderDisclaimer();
    renderHero();
    renderKpis(reportData);
    renderSummaryStrip(reportData);
    renderConclusions(reportData);
    renderQuality(reportData);
    renderNarratives(reportData);
    renderNeighborhoodTable(reportData);
    renderMarketInsights(reportData);
    renderNeighborhoodRankings(reportData);
    try {
      await ensureChartJs();
      renderCharts(reportData);
    } catch (error) {
      console.error("annual_charts_unavailable", error);
    }
    renderFormulas(reportData);
    renderMethodology(reportData);
    renderRefreshNote(reportData);
    if (animateCounts) {
      window.MetrikSite?.initCountUp?.(document.getElementById("annual-kpis"));
    }
  }

  function setLoadState(state) {
    const loading = document.getElementById("annual-loading");
    const error = document.getElementById("annual-error");
    const content = document.getElementById("annual-content");
    if (loading) loading.hidden = state !== "loading";
    if (error) error.hidden = state !== "error";
    if (content) {
      content.hidden = state !== "ready";
      if (state === "ready") content.classList.add("content-fade-in");
    }
  }

  async function loadReport({ silent = false } = {}) {
    if (!silent) setLoadState("loading");
    try {
      let data;
      if (window.MetrikApiCache && !silent) {
        data = await window.MetrikApiCache.getJson("/api/reports/annual_data", {
          ttlMs: 45_000,
          cacheKey: "annual_data",
        });
      } else {
        const res = await fetch(`/api/reports/annual_data?_=${Date.now()}`, {
          cache: silent ? "no-store" : "default",
        });
        if (!res.ok) throw new Error(`Annual report request failed: ${res.status}`);
        data = await res.json();
      }
      const revision = data.data_revision || data.generated_at;
      if (silent && revision && revision === lastDataRevision) return;
      lastDataRevision = revision;
      reportData = data;
      await renderAll({ animateCounts: !silent });
      setLoadState("ready");
    } catch (error) {
      console.error("annual_report_load_failed", error);
      if (!silent) {
        setLoadState("error");
      }
    }
  }

  async function initReport() {
    document.getElementById("annual-retry")?.addEventListener("click", () => loadReport());
    await loadReport();
    setInterval(() => loadReport({ silent: true }), POLL_MS);
  }

  document.addEventListener("metrik:langchange", () => {
    window.MetrikI18n.apply(document);
    renderPdfButtons();
    void renderAll({ animateCounts: true });
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initReport);
  } else {
    initReport();
  }
})();
