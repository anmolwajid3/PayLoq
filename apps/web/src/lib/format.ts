export function fmtEur(v: number, lang: "fi" | "en" = "fi"): string {
  return new Intl.NumberFormat(lang === "fi" ? "fi-FI" : "en-IE", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(v);
}

export function fmtNum(v: number, lang: "fi" | "en" = "fi", digits = 0): string {
  return new Intl.NumberFormat(lang === "fi" ? "fi-FI" : "en-IE", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(v);
}

export function fmtPct(v: number, lang: "fi" | "en" = "fi"): string {
  return `${fmtNum(v * 100, lang, 1)} %`;
}
