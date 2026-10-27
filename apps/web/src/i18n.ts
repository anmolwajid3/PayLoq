export type Lang = "fi" | "en";

const dict = {
  brandTagline: {
    fi: "Synteettiset talousaineistot — koodi laskee, malli tulkitsee.",
    en: "Synthetic financial datasets — code calculates, the model interprets.",
  },
  login: { fi: "Kirjaudu", en: "Sign in" },
  logout: { fi: "Kirjaudu ulos", en: "Sign out" },
  username: { fi: "Käyttäjätunnus", en: "Username" },
  password: { fi: "Salasana", en: "Password" },
  scenarios: { fi: "Skenaariot", en: "Scenarios" },
  generate: { fi: "Generoi", en: "Generate" },
  runs: { fi: "Ajot", en: "Runs" },
  open: { fi: "Avaa", en: "Open" },
  preset: { fi: "Valmis", en: "Preset" },
  custom: { fi: "Oma", en: "Custom" },
  generatePreset: { fi: "Generoi paketti", en: "Generate pack" },
  fromText: { fi: "Tekstistä (NL)", en: "From text (NL)" },
  description: { fi: "Kuvaus", en: "Description" },
  validation: { fi: "Validointi", en: "Validation" },
  ok: { fi: "OK", en: "OK" },
  failed: { fi: "Epäonnistui", en: "Failed" },
  cashHistory: { fi: "Kassahistoria", en: "Cash history" },
  cashProjection: { fi: "Kassaprojektio", en: "Cash projection" },
  artifacts: { fi: "Tiedostot", en: "Artifacts" },
  download: { fi: "Lataa", en: "Download" },
  viewJson: { fi: "Näytä JSON", en: "View JSON" },
  llmStub: { fi: "Stub (CPU)", en: "Stub (CPU)" },
  llmOllama: { fi: "Ollama", en: "Ollama" },
  language: { fi: "Kieli", en: "Language" },
  months: { fi: "Kuukaudet", en: "Months" },
  industry: { fi: "Toimiala", en: "Industry" },
  runGenerate: { fi: "Käynnistä generointi", en: "Run generation" },
  back: { fi: "Takaisin", en: "Back" },
  loginHint: {
    fi: "PoC-kirjautuminen — oletus payloq / payloq",
    en: "PoC login — default payloq / payloq",
  },
  heroCta: { fi: "Selaa skenaarioita", en: "Browse scenarios" },
  heroSecondary: { fi: "Generoi tekstistä", en: "Generate from text" },
  openInvoices: { fi: "Avoimet laskut", en: "Open invoices" },
  lastCash: { fi: "Viimeisin kassa", en: "Latest cash" },
  status: { fi: "Tila", en: "Status" },
  emptyRuns: { fi: "Ei ajoja vielä.", en: "No runs yet." },
  loading: { fi: "Ladataan…", en: "Loading…" },
  error: { fi: "Virhe", en: "Error" },
} as const;

export type MsgKey = keyof typeof dict;

export function t(key: MsgKey, lang: Lang): string {
  return dict[key][lang];
}
