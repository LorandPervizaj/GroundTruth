/** Shared Chart.js helpers for Metrik market / stats / compare / yield pages. */
(function () {
  const CHART_SRC = "/static/chart.umd.min.js?v=4.4.8";
  let chartLoader = null;
  const instances = new WeakMap();

  function theme() {
    return window.MetrikTheme?.chartTheme?.() || {
      primary: "#1a4d38",
      secondary: "#8bb9a3",
      tertiary: "#5a7a6a",
      primaryFill: "rgba(26, 77, 56, 0.05)",
      tertiaryFill: "rgba(90, 122, 106, 0.08)",
      grid: "#e5e5e0",
      tick: "#6b6b6b",
      label: "#333333",
      pointBorder: "#ffffff",
      outlier: "#b45309",
    };
  }

  function ensureChartJs() {
    if (window.Chart) return Promise.resolve(window.Chart);
    if (chartLoader) return chartLoader;
    chartLoader = new Promise((resolve, reject) => {
      const existing = document.querySelector(`script[src^="/static/chart.umd.min.js"]`);
      if (existing && window.Chart) {
        resolve(window.Chart);
        return;
      }
      const script = document.createElement("script");
      script.src = CHART_SRC;
      script.async = true;
      script.onload = () => {
        if (!window.Chart) {
          reject(new Error("Chart.js loaded without Chart global"));
          return;
        }
        resolve(window.Chart);
      };
      script.onerror = () => reject(new Error("Chart.js failed to load"));
      document.head.appendChild(script);
    });
    return chartLoader;
  }

  function destroy(canvas) {
    if (!canvas) return;
    const existing = instances.get(canvas) || window.Chart?.getChart?.(canvas);
    if (existing) {
      existing.destroy();
      instances.delete(canvas);
    }
    canvas.hidden = true;
  }

  function setNote(el, text) {
    if (!el) return;
    el.textContent = text == null ? "" : String(text);
  }

  function showChart(wrap) {
    if (!wrap) return;
    wrap.hidden = false;
    wrap.classList?.remove?.("hidden");
    const empty = wrap.querySelector?.(".chart-empty-msg");
    if (empty) empty.hidden = true;
    const canvas = wrap.querySelector?.("canvas");
    if (canvas) canvas.hidden = false;
  }

  function hideChart(wrap, message) {
    if (!wrap) return;
    const canvas = wrap.querySelector?.("canvas");
    if (canvas) {
      destroy(canvas);
      canvas.hidden = true;
    }
    const empty = wrap.querySelector?.(".chart-empty-msg");
    if (empty) {
      empty.hidden = false;
      if (message != null) empty.textContent = String(message);
    }
  }

  function finiteValues(values) {
    return (values || [])
      .map((v) => (v == null ? null : Number(v)))
      .filter((v) => v != null && Number.isFinite(v));
  }

  function externalTooltip(tooltipBuilder) {
    if (typeof tooltipBuilder !== "function") return undefined;
    return function (context) {
      const { chart, tooltip } = context;
      let el = chart.canvas.parentNode?.querySelector?.(".metrik-chart-tooltip");
      if (!el) {
        el = document.createElement("div");
        el.className = "metrik-chart-tooltip";
        el.setAttribute("role", "tooltip");
        chart.canvas.parentNode?.appendChild(el);
      }
      if (tooltip.opacity === 0 || !tooltip.dataPoints?.length) {
        el.hidden = true;
        return;
      }
      const built = tooltipBuilder(tooltip.dataPoints) || { title: "", lines: [] };
      const lines = (built.lines || []).filter(Boolean);
      el.innerHTML = "";
      if (built.title) {
        const title = document.createElement("div");
        title.className = "metrik-chart-tooltip-title";
        title.textContent = built.title;
        el.appendChild(title);
      }
      for (const line of lines) {
        const row = document.createElement("div");
        row.textContent = line;
        el.appendChild(row);
      }
      const { offsetLeft: left, offsetTop: top } = chart.canvas;
      el.style.left = `${left + tooltip.caretX}px`;
      el.style.top = `${top + tooltip.caretY}px`;
      el.hidden = false;
    };
  }

  function baseOptions({ beginAtZero = true, tooltipBuilder, indexAxis = "x", compact = false } = {}) {
    const colors = theme();
    return {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis,
      layout: { padding: { top: compact ? 8 : 18, right: 4, left: 2, bottom: 2 } },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: tooltipBuilder
          ? {
              enabled: false,
              external: externalTooltip(tooltipBuilder),
            }
          : {
              callbacks: {},
            },
      },
      scales: {
        x: {
          beginAtZero: indexAxis === "y" ? beginAtZero : false,
          grid: { display: indexAxis === "y", color: colors.grid, drawBorder: false },
          border: { color: colors.grid },
          ticks: {
            color: colors.tick,
            font: { family: "inherit", size: 11 },
            maxRotation: 0,
            autoSkip: true,
          },
        },
        y: {
          beginAtZero: indexAxis === "x" ? beginAtZero : false,
          grace: indexAxis === "x" ? "12%" : undefined,
          grid: { color: colors.grid, drawBorder: false },
          border: { display: false },
          ticks: {
            color: colors.tick,
            font: { family: "inherit", size: 11 },
          },
        },
      },
    };
  }

  function remember(canvas, chart) {
    instances.set(canvas, chart);
    canvas.hidden = false;
    return chart;
  }

  function createSparkline(canvas, { values, color } = {}) {
    if (!canvas || !window.Chart) return null;
    destroy(canvas);
    const clean = (values || []).map((v) => (v == null || !Number.isFinite(Number(v)) ? null : Number(v)));
    const present = clean.filter((v) => v != null);
    if (present.length < 2) {
      canvas.hidden = true;
      return null;
    }
    const stroke = color || theme().primary;
    const chart = new window.Chart(canvas, {
      type: "line",
      data: {
        labels: clean.map((_, i) => String(i)),
        datasets: [
          {
            data: clean,
            borderColor: stroke,
            backgroundColor: "transparent",
            borderWidth: 1.5,
            pointRadius: 0,
            pointHoverRadius: 0,
            tension: 0.3,
            spanGaps: true,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: {
          x: { display: false },
          y: { display: false },
        },
        elements: { line: { borderJoinStyle: "round" } },
      },
    });
    return remember(canvas, chart);
  }

  function createLineChart(canvas, opts = {}) {
    if (!canvas || !window.Chart) return null;
    destroy(canvas);
    const colors = theme();
    const datasets = (opts.datasets || []).map((ds) => ({
      label: ds.label || "",
      data: ds.data || [],
      borderColor: ds.borderColor || colors.primary,
      backgroundColor: ds.backgroundColor || colors.primaryFill,
      fill: ds.fill !== false,
      tension: 0.25,
      borderWidth: 2,
      pointRadius: 1.5,
      pointHoverRadius: 4,
      pointBorderColor: colors.pointBorder,
      pointBackgroundColor: ds.borderColor || colors.primary,
      spanGaps: true,
    }));
    const options = baseOptions({
      beginAtZero: opts.beginAtZero === true,
      tooltipBuilder: opts.tooltipBuilder,
    });
    if (opts.beginAtZero === false && options.scales?.y) {
      options.scales.y.beginAtZero = false;
    }
    const chart = new window.Chart(canvas, {
      type: "line",
      data: { labels: opts.labels || [], datasets },
      options,
    });
    return remember(canvas, chart);
  }

  /* Compatibility for the production Market UI. The production templates and
     lookup.js call this helper, but the helper file was omitted from that Git
     snapshot. Keep the adapter here so the restored UI can consume the current
     backend distribution payload without changing its markup or layout. */
  function createHistogram(canvas, opts = {}) {
    if (!canvas || !window.Chart) return null;
    destroy(canvas);
    const colors = theme();
    const values = (opts.values || []).map((v) =>
      v == null || !Number.isFinite(Number(v)) ? 0 : Number(v)
    );
    if (!values.some((v) => v > 0)) {
      canvas.hidden = true;
      return null;
    }
    const centers = (opts.binCenters || []).map(Number);
    const median = Number(opts.median);
    const medianIndex = Number.isFinite(median) && centers.length
      ? centers.reduce((best, value, index) =>
          Math.abs(value - median) < Math.abs(centers[best] - median) ? index : best, 0)
      : null;
    const medianMarker = {
      id: "metrikMedianMarker",
      afterDatasetsDraw(chart) {
        if (medianIndex == null) return;
        const { ctx, chartArea, scales } = chart;
        const x = scales.x.getPixelForValue(medianIndex);
        ctx.save();
        ctx.strokeStyle = colors.tertiary;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(x, chartArea.top);
        ctx.lineTo(x, chartArea.bottom);
        ctx.stroke();
        if (opts.medianLabel) {
          ctx.setLineDash([]);
          ctx.fillStyle = colors.label;
          ctx.font = "11px sans-serif";
          ctx.fillText(String(opts.medianLabel), Math.min(x + 5, chartArea.right - 54), chartArea.top + 12);
        }
        ctx.restore();
      },
    };
    const chart = new window.Chart(canvas, {
      type: "bar",
      data: {
        labels: opts.labels || [],
        datasets: [{
          data: values,
          backgroundColor: opts.color || colors.primary,
          borderSkipped: false,
          borderRadius: 2,
          barPercentage: 1,
          categoryPercentage: 0.94,
        }],
      },
      options: baseOptions({ beginAtZero: true, tooltipBuilder: opts.tooltipBuilder }),
      plugins: [medianMarker],
    });
    return remember(canvas, chart);
  }

  function createHorizontalBarChart(canvas, opts = {}) {
    if (!canvas || !window.Chart) return null;
    destroy(canvas);
    const colors = theme();
    const values = (opts.values || []).map((v) => (v == null || !Number.isFinite(Number(v)) ? null : Number(v)));
    if (!values.some((v) => v != null)) {
      canvas.hidden = true;
      return null;
    }
    const options = baseOptions({
      beginAtZero: true,
      tooltipBuilder: opts.tooltipBuilder,
      indexAxis: "y",
    });
    if (typeof opts.formatTick === "function") {
      options.scales.x.ticks.callback = (v) => opts.formatTick(v);
    }
    const chart = new window.Chart(canvas, {
      type: "bar",
      data: {
        labels: opts.labels || [],
        datasets: [
          {
            label: opts.label || "",
            data: values,
            backgroundColor: opts.color || colors.primary,
            hoverBackgroundColor: colors.tertiary,
            borderSkipped: false,
            borderRadius: 4,
            maxBarThickness: 28,
          },
        ],
      },
      options,
    });
    return remember(canvas, chart);
  }

  window.MetrikCharts = {
    ensureChartJs,
    theme,
    destroy,
    setNote,
    showChart,
    hideChart,
    createSparkline,
    createLineChart,
    createHistogram,
    createHorizontalBarChart,
    finiteValues,
    remember,
    buildExternalTooltip: externalTooltip,
  };

  // Production pages and their browser contract expect the self-hosted Chart
  // global to be ready after deferred scripts finish loading.
  ensureChartJs().catch((error) => console.error("Chart.js failed to initialize", error));
})();
