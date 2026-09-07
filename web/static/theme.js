/** Read design tokens from CSS custom properties for Chart.js and other JS. */
(function () {
  function readVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function chartTheme() {
    return {
      primary: readVar("--chart-primary"),
      secondary: readVar("--chart-secondary"),
      tertiary: readVar("--chart-tertiary"),
      primaryFill: readVar("--chart-primary-fill"),
      tertiaryFill: readVar("--chart-tertiary-fill"),
      grid: readVar("--chart-grid"),
      tick: readVar("--chart-tick"),
      label: readVar("--chart-label"),
      pointBorder: readVar("--chart-point-border"),
      outlier: readVar("--outlier"),
    };
  }

  window.MetrikTheme = { readVar, chartTheme };
})();
