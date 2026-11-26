const API_BASE = import.meta.env.VITE_API_BASE?.replace(/\/$/, "") || "";

export type Scenario = {
  id: number;
  slug: string;
  title_fi: string;
  title_en: string;
  description_fi: string;
  description_en: string;
  is_preset: boolean;
  input_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type Run = {
  id: number;
  scenario_id: number | null;
  source: string;
  llm_adapter: string;
  llm_model: string | null;
  llm_fallback_note: string | null;
  seed: number;
  status: string;
  error_message: string | null;
  artifact_dir: string | null;
  validation_ok: boolean | null;
  validation_json: {
    ok: boolean;
    issues: { code: string; message: string; severity: string }[];
  } | null;
  pack_summary: {
    scenario?: string;
    months?: number;
    as_of?: string;
    last_cash?: number;
    last_revenue?: number;
    open_invoices?: number;
    balance_history?: { date: string; balance: number }[];
    projection?: {
      week: number;
      week_end: string;
      sales_inflow: number;
      purchase_outflow: number;
      projected_balance: number;
    }[];
    description?: { fi: string; en: string };
    language?: "fi" | "en" | string;
    parameters?: Record<string, unknown>;
    options?: Record<string, unknown>;
    field_summary?: {
      input_name: string;
      output_location: string;
      label: string;
      label_en?: string;
      label_fi?: string;
      value: unknown;
      display: string;
      source?: string | null;
      format?: string;
    }[];
    nl_soft_warnings?: {
      code: string;
      severity?: string;
      message_fi?: string;
      message_en?: string;
      message?: string;
    }[];
  } | null;
  from_text: string | null;
  created_at: string;
  artifacts: string[];
  comparison?: ModelComparison | null;
  progress?: RunProgress | null;
};

export type RunProgress = {
  percent: number;
  stage: string;
  label_en: string;
  label_fi: string;
  done: boolean;
  error?: string | null;
};

export type ModelComparisonRow = {
  model: string;
  parameter_score: number | null;
  reading_score: number | null;
  mom_score: number | null;
  interpretation_score: number | null;
  interpretation_axes?: Record<string, number>;
  fi_quality_score: number | null;
  fi_band?: string;
  latency_ms?: number;
  composite_score?: number;
  interpretation_answer?: string;
  notes?: string;
  score_rationale?: string;
  judge_model?: string | null;
  judge_score?: number | null;
  judge_axes?: Record<string, number>;
  judge_notes?: string;
  parameter_field_scores?: Record<string, number>;
};

export type ModelComparison = {
  version?: number;
  pack_model?: string;
  recommended_model?: string | null;
  judge_model?: string | null;
  judge_role?: string;
  judge_skipped?: string | null;
  score_weights?: Record<string, number>;
  models: ModelComparisonRow[];
  skipped?: { model: string; reason: string }[];
  shortlist_default?: string[];
  fi_band_legend?: Record<string, string>;
};

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("payloq_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function login(username: string, password: string) {
  return request<{
    access_token: string;
    username: string;
    display_name: string;
  }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export async function logout() {
  return request<{ cleared_company_data: boolean }>("/api/auth/logout", {
    method: "POST",
    body: "{}",
  });
}

export type CompanySession = {
  username: string;
  created_at: number;
  expires_at: number;
  ttl_remaining_s: number;
  filenames: string[];
  notes: string[];
  model: string | null;
  has_figures: boolean;
  figure_summary: Record<string, unknown>;
  situation_report: string | null;
  chat: { role: string; content: string; at: number }[];
};

export async function getCompanySession() {
  return request<CompanySession>("/api/company-data/session");
}

export async function discardCompanySession() {
  return request<{ cleared: boolean }>("/api/company-data/session", {
    method: "DELETE",
  });
}

export async function uploadCompanyFiles(files: File[]) {
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  const token = localStorage.getItem("payloq_token");
  const res = await fetch(`${API_BASE}/api/company-data/upload`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: fd,
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<CompanySession>;
}

export async function companySituationReport(body: {
  language: "fi" | "en";
  ollama_model?: string;
}) {
  return request<{ answer: string; model: string | null; session: CompanySession }>(
    "/api/company-data/situation-report",
    { method: "POST", body: JSON.stringify(body) },
  );
}

export async function companyChat(body: {
  question: string;
  language: "fi" | "en";
  ollama_model?: string;
}) {
  return request<{ answer: string; model: string | null; session: CompanySession }>(
    "/api/company-data/chat",
    { method: "POST", body: JSON.stringify(body) },
  );
}

export async function me() {
  return request<{ username: string; display_name: string }>("/api/auth/me");
}

export async function listScenarios() {
  return request<Scenario[]>("/api/scenarios");
}

export async function getScenario(slug: string) {
  return request<Scenario>(`/api/scenarios/${encodeURIComponent(slug)}`);
}

export async function listRuns(limit = 50) {
  return request<Run[]>(`/api/runs?limit=${limit}`);
}

export async function getRun(id: number) {
  return request<Run>(`/api/runs/${id}`);
}

export async function deleteRun(id: number) {
  return request<{ deleted: boolean }>(`/api/runs/${id}`, { method: "DELETE" });
}

export async function generatePreset(
  scenario_slug: string,
  opts?: {
    seed?: number;
    language?: "fi" | "en";
    compare?: boolean;
    compare_models?: string[];
    background?: boolean;
  },
) {
  return request<Run>("/api/generate/preset", {
    method: "POST",
    body: JSON.stringify({
      scenario_slug,
      seed: opts?.seed ?? 42,
      write_xlsx: true,
      language: opts?.language ?? "fi",
      compare: opts?.compare ?? true,
      compare_models: opts?.compare_models,
      background: opts?.background ?? true,
    }),
  });
}

export async function generateFromText(body: {
  text: string;
  llm: "ollama";
  ollama_model: string;
  language: "fi" | "en";
  industry: string;
  company_size: string;
  months: number;
  seed: number;
  compare?: boolean;
  compare_models?: string[];
  background?: boolean;
}) {
  return request<Run>("/api/generate/from-text", {
    method: "POST",
    body: JSON.stringify({ ...body, write_xlsx: true, background: body.background ?? true }),
  });
}

export type OllamaModel = {
  name: string;
  size?: number | null;
  modified_at?: string | null;
  digest?: string | null;
  parameter_size?: string | null;
  family?: string | null;
};

export type OllamaModelsResponse = {
  available: boolean;
  host: string;
  models: OllamaModel[];
  error: string | null;
  recommended: string[];
  compare_shortlist?: string[];
};

export async function listLlmModels() {
  return request<OllamaModelsResponse>("/api/llm/models");
}

export type ChatPreset = { id: string; question: string };

export type ChatResponse = {
  question: string;
  answer: string;
  figures: Record<string, unknown>;
  preset: string | null;
  llm_adapter: string;
  llm_model: string | null;
  fallback_note: string | null;
  metrics: Record<string, unknown> | null;
};

export async function listChatPresets(language: "fi" | "en" = "fi") {
  return request<ChatPreset[]>(`/api/chat/presets?language=${language}`);
}

export async function listChatSuggestions(
  runId: number,
  body: {
    language: "fi" | "en";
    prior_questions?: string[];
    limit?: number;
  },
) {
  return request<ChatPreset[]>(`/api/runs/${runId}/chat/suggestions`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function chatOnRun(
  runId: number,
  body: {
    question?: string;
    preset?: "cash_drop" | "cash_negative";
    language: "fi" | "en";
  },
) {
  return request<ChatResponse>(`/api/runs/${runId}/chat`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}


export function artifactUrl(runId: number, filename: string) {
  return `${API_BASE}/api/runs/${runId}/artifacts/${encodeURIComponent(filename)}`;
}

export async function fetchArtifactText(runId: number, filename: string) {
  const res = await fetch(artifactUrl(runId, filename), { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to load artifact");
  return res.text();
}

export async function downloadArtifact(runId: number, filename: string) {
  const res = await fetch(artifactUrl(runId, filename), { headers: authHeaders() });
  if (!res.ok) throw new Error("Download failed");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
