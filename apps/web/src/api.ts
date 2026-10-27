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
    parameters?: Record<string, unknown>;
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

export async function me() {
  return request<{ username: string; display_name: string }>("/api/auth/me");
}

export async function listScenarios() {
  return request<Scenario[]>("/api/scenarios");
}

export async function getScenario(slug: string) {
  return request<Scenario>(`/api/scenarios/${encodeURIComponent(slug)}`);
}

export async function listRuns() {
  return request<Run[]>("/api/runs");
}

export async function getRun(id: number) {
  return request<Run>(`/api/runs/${id}`);
}

export async function generatePreset(scenario_slug: string) {
  return request<Run>("/api/generate/preset", {
    method: "POST",
    body: JSON.stringify({
      scenario_slug,
      seed: 42,
      write_xlsx: true,
      write_journal: true,
    }),
  });
}

export async function generateFromText(body: {
  text: string;
  llm: "stub" | "ollama";
  language: "fi" | "en";
  industry: string;
  months: number;
}) {
  return request<Run>("/api/generate/from-text", {
    method: "POST",
    body: JSON.stringify({ ...body, seed: 42, write_xlsx: true, write_journal: true }),
  });
}

export type ChatPreset = { id: string; question: string };

export type ChatResponse = {
  question: string;
  answer: string;
  figures: Record<string, unknown>;
  preset: string | null;
  llm_adapter: string;
  fallback_note: string | null;
  metrics: Record<string, unknown> | null;
};

export async function listChatPresets(language: "fi" | "en" = "fi") {
  return request<ChatPreset[]>(`/api/chat/presets?language=${language}`);
}

export async function chatOnRun(
  runId: number,
  body: {
    question?: string;
    preset?: "cash_drop" | "cash_negative";
    language: "fi" | "en";
    llm: "stub" | "ollama";
  },
) {
  return request<ChatResponse>(`/api/runs/${runId}/chat`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function ensureJournal(runId: number) {
  return request<Run>(`/api/runs/${runId}/journal`, { method: "POST" });
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
