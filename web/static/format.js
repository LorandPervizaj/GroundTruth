/** Shared number/currency formatting — rent/sale rounding policy. */
(function () {
  function locale() {
    const lang = window.MetrikI18n?.getLang?.() || "sq";
    return lang === "sq" ? "sq-AL" : "en";
  }

  function int(n) {
    if (n == null || Number.isNaN(Number(n))) return "-";
    return Math.round(Number(n)).toLocaleString(locale());
  }

  function decimal(n, digits = 1) {
    if (n == null || Number.isNaN(Number(n))) return "-";
    return Number(n).toLocaleString(locale(), {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  }

  function roundRent(n) {
    return Math.round(Number(n) / 10) * 10;
  }

  function roundSale(n) {
    return Math.round(Number(n) / 1000) * 1000;
  }

  function roundSalePsm(n) {
    return Math.round(Number(n) / 10) * 10;
  }

  function roundRentPsm(n) {
    if (n == null || Number.isNaN(Number(n))) return null;
    const v = Math.round(Number(n));
    return v >= 1 ? v : null;
  }

  function roundArea(n) {
    return Math.round(Number(n) / 50) * 50;
  }

  /** Individual listing/comparable — show actual m² (valuation uses ±5 m² bands). */
  function roundAreaListing(n) {
    return Math.round(Number(n));
  }

  function euroRent(n) {
    if (n == null || Number.isNaN(Number(n))) return "-";
    return `€${int(roundRent(n))}`;
  }

  function euroSale(n) {
    if (n == null || Number.isNaN(Number(n))) return "-";
    return `€${int(roundSale(n))}`;
  }

  /** @deprecated use euroRent or euroSale */
  function euro(n) {
    return euroSale(n);
  }

  function euroSalePsm(n) {
    if (n == null || Number.isNaN(Number(n))) return "-";
    return `€${int(roundSalePsm(n))}/m²`;
  }

  function euroRentPsm(n) {
    const num = roundRentPsm(n);
    if (num == null) return "—";
    return `€${int(num)}/m²`;
  }

  /** @deprecated use euroSalePsm or euroRentPsm */
  function euroPsm(n) {
    const num = Number(n);
    if (n == null || Number.isNaN(num)) return "-";
    if (num < 100) return euroRentPsm(num);
    return euroSalePsm(num);
  }

  function area(n) {
    if (n == null || Number.isNaN(Number(n))) return "-";
    return `${int(roundArea(n))} m²`;
  }

  function areaListing(n) {
    if (n == null || Number.isNaN(Number(n))) return "-";
    return `${int(roundAreaListing(n))} m²`;
  }

  function percent(n) {
    if (n == null || Number.isNaN(Number(n))) return "-";
    return `${Math.round(Number(n))}%`;
  }

  function dateTime(iso) {
    if (!iso) return "-";
    const lang = window.MetrikI18n?.getLang?.() || "sq";
    const loc = lang === "sq" ? "sq-AL" : "en-GB";
    return new Date(iso).toLocaleString(loc, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function dateShort(iso) {
    if (!iso) return "-";
    const lang = window.MetrikI18n?.getLang?.() || "sq";
    const loc = lang === "sq" ? "sq-AL" : "en-GB";
    return new Date(iso).toLocaleDateString(loc, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }

  window.MetrikFormat = {
    locale,
    int,
    decimal,
    roundRent,
    roundSale,
    roundSalePsm,
    roundRentPsm,
    roundArea,
    roundAreaListing,
    euro,
    euroRent,
    euroSale,
    euroPsm,
    euroSalePsm,
    euroRentPsm,
    area,
    areaListing,
    percent,
    dateTime,
    dateShort,
  };
})();
