import type {
  AnalysisStatus,
  AuditFocusPayload,
  AuditProfilePayload,
  AuditTimelineItem,
  ChatAnswerPayload,
  DashboardPayload,
  DocumentExtractItem,
  DocumentListItem,
  EnterpriseBootstrapPayload,
  EnterpriseDetail,
  EnterpriseEventsPayload,
  EnterpriseReadinessPayload,
  EnterpriseSearchItem,
  FinancialAnalysisPayload,
  RiskResultPayload,
  RiskSummaryPayload,
  SyncCompanyPayload,
} from "@auditpilot/shared-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const FINANCIAL_ANALYSIS_TTL_MS = 20_000;

export type ApiRequestOptions = {
  signal?: AbortSignal;
  force?: boolean;
};

type FinancialAnalysisCacheEntry = {
  data: FinancialAnalysisPayload;
  expiresAt: number;
};

const financialAnalysisCache = new Map<number, FinancialAnalysisCacheEntry>();
const financialAnalysisInFlight = new Map<number, Promise<FinancialAnalysisPayload>>();

async function readErrorMessage(response: Response): Promise<string> {
  const text = await response.text();
  if (!text) {
    return `请求失败，状态码 ${response.status}。`;
  }
  try {
    const payload = JSON.parse(text) as { detail?: string };
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      return payload.detail.trim();
    }
  } catch {
    // Ignore JSON parse failures and return raw text.
  }
  return text;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function raceWithAbort<T>(promise: Promise<T>, signal?: AbortSignal): Promise<T> {
  if (!signal) {
    return promise;
  }
  if (signal.aborted) {
    return Promise.reject(new DOMException("The operation was aborted.", "AbortError"));
  }
  return new Promise<T>((resolve, reject) => {
    const onAbort = () => reject(new DOMException("The operation was aborted.", "AbortError"));
    signal.addEventListener("abort", onAbort, { once: true });
    promise.then(
      (value) => {
        signal.removeEventListener("abort", onAbort);
        resolve(value);
      },
      (error) => {
        signal.removeEventListener("abort", onAbort);
        reject(error);
      },
    );
  });
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    const response = await fetch(`${API_BASE_URL}/api${path}`, {
      ...init,
      cache: "no-store",
    });
    if (!response.ok) {
      throw new Error(await readErrorMessage(response));
    }
    return (await response.json()) as T;
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
    if (error instanceof TypeError) {
      throw new Error("后端 API 不可访问，请检查 NEXT_PUBLIC_API_BASE_URL、后端服务状态和网络连通性。");
    }
    throw error;
  }
}

function getCachedFinancialAnalysis(enterpriseId: number): FinancialAnalysisPayload | null {
  const cached = financialAnalysisCache.get(enterpriseId);
  if (!cached) {
    return null;
  }
  if (cached.expiresAt <= Date.now()) {
    financialAnalysisCache.delete(enterpriseId);
    return null;
  }
  return cached.data;
}

function cacheFinancialAnalysis(enterpriseId: number, data: FinancialAnalysisPayload): FinancialAnalysisPayload {
  financialAnalysisCache.set(enterpriseId, {
    data,
    expiresAt: Date.now() + FINANCIAL_ANALYSIS_TTL_MS,
  });
  return data;
}

async function fetchFinancialAnalysis(enterpriseId: number): Promise<FinancialAnalysisPayload> {
  const payload = await request<FinancialAnalysisPayload>(`/enterprises/${enterpriseId}/financial-analysis`);
  return cacheFinancialAnalysis(enterpriseId, payload);
}

async function getFinancialAnalysis(
  enterpriseId: number,
  options?: ApiRequestOptions,
): Promise<FinancialAnalysisPayload> {
  if (!options?.force) {
    const cached = getCachedFinancialAnalysis(enterpriseId);
    if (cached) {
      return cached;
    }
  } else {
    financialAnalysisCache.delete(enterpriseId);
  }

  const existing = financialAnalysisInFlight.get(enterpriseId);
  if (existing) {
    return raceWithAbort(existing, options?.signal);
  }

  const promise = fetchFinancialAnalysis(enterpriseId).finally(() => {
    financialAnalysisInFlight.delete(enterpriseId);
  });
  financialAnalysisInFlight.set(enterpriseId, promise);
  return raceWithAbort(promise, options?.signal);
}

export type RiskRunResponse = {
  run: { run_id: number; status: AnalysisStatus | string; summary: string };
  results: RiskResultPayload[];
};

export const api = {
  invalidateFinancialAnalysis(enterpriseId?: number) {
    if (typeof enterpriseId === "number") {
      financialAnalysisCache.delete(enterpriseId);
      return;
    }
    financialAnalysisCache.clear();
  },
  listEnterprises: (query?: string, options?: ApiRequestOptions) =>
    request<EnterpriseSearchItem[]>(
      `/enterprises${query?.trim() ? `?q=${encodeURIComponent(query.trim())}` : ""}`,
      { signal: options?.signal },
    ),
  bootstrapEnterprise: (payload: { ticker?: string; name?: string }, options?: ApiRequestOptions) =>
    request<EnterpriseBootstrapPayload>(`/enterprises/bootstrap`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: options?.signal,
    }),
  getEnterprise: (enterpriseId: number, options?: ApiRequestOptions) =>
    request<EnterpriseDetail>(`/enterprises/${enterpriseId}`, { signal: options?.signal }),
  getDashboard: (enterpriseId: number, options?: ApiRequestOptions) =>
    request<DashboardPayload>(`/enterprises/${enterpriseId}/dashboard`, { signal: options?.signal }),
  getAuditProfile: (enterpriseId: number, options?: ApiRequestOptions) =>
    request<AuditProfilePayload>(`/companies/${enterpriseId}/audit-profile`, { signal: options?.signal }),
  getTimeline: (enterpriseId: number, options?: ApiRequestOptions) =>
    request<AuditTimelineItem[]>(`/companies/${enterpriseId}/timeline`, { signal: options?.signal }),
  getRiskSummary: (enterpriseId: number, options?: ApiRequestOptions) =>
    request<RiskSummaryPayload>(`/companies/${enterpriseId}/risk-summary`, { signal: options?.signal }),
  getReadiness: (enterpriseId: number, options?: ApiRequestOptions) =>
    request<EnterpriseReadinessPayload>(`/companies/${enterpriseId}/readiness`, { signal: options?.signal }),
  getEnterpriseDocuments: (enterpriseId: number, options?: ApiRequestOptions) =>
    request<DocumentListItem[]>(`/enterprises/${enterpriseId}/documents`, { signal: options?.signal }),
  getEnterpriseEvents: (enterpriseId: number, options?: ApiRequestOptions) =>
    request<EnterpriseEventsPayload>(`/enterprises/${enterpriseId}/events`, { signal: options?.signal }),
  getFinancialAnalysis,
  syncCompany: (enterpriseId: number, sources: string[] = ["akshare_fast", "cninfo"], options?: ApiRequestOptions) =>
    request<SyncCompanyPayload>(`/sync/company`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_id: enterpriseId, sources }),
      signal: options?.signal,
    }),
  runRiskAnalysis: (enterpriseId: number, options?: ApiRequestOptions) =>
    request<RiskRunResponse>(`/risk-analysis/${enterpriseId}/run`, {
      method: "POST",
      signal: options?.signal,
    }),
  getRiskResults: (enterpriseId: number, options?: ApiRequestOptions) =>
    request<RiskResultPayload[]>(`/risk-analysis/${enterpriseId}/results`, { signal: options?.signal }),
  getAuditFocus: (enterpriseId: number, options?: ApiRequestOptions) =>
    request<AuditFocusPayload>(`/audit-focus/${enterpriseId}`, { signal: options?.signal }),
  getReport: (enterpriseId: number, format = "json", options?: ApiRequestOptions) =>
    request(`/reports/${enterpriseId}?format=${format}`, { signal: options?.signal }),
  ingestFinancial: (enterpriseId: number, options?: ApiRequestOptions) =>
    request(`/ingestion/financial`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enterprise_id: enterpriseId, provider: "akshare", include_quarterly: true }),
      signal: options?.signal,
    }),
  parseDocument: (documentId: number, options?: ApiRequestOptions) =>
    request(`/documents/${documentId}/parse`, {
      method: "POST",
      signal: options?.signal,
    }),
  getDocumentExtracts: (documentId: number, options?: ApiRequestOptions) =>
    request<{ document_id: number; extracts: DocumentExtractItem[] }>(`/documents/${documentId}/extracts`, {
      signal: options?.signal,
    }),
  overrideDocumentClassification: (documentId: number, classifiedType: string, options?: ApiRequestOptions) =>
    request<{ document_id: number; classified_type: string }>(`/documents/${documentId}/classification`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ classified_type: classifiedType }),
      signal: options?.signal,
    }),
  overrideExtractEventType: (documentId: number, evidenceSpanId: string, eventType: string, options?: ApiRequestOptions) =>
    request<{ document_id: number; evidence_span_id: string; event_type: string }>(
      `/documents/${documentId}/extracts/${encodeURIComponent(evidenceSpanId)}/event-type`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ event_type: eventType }),
        signal: options?.signal,
      },
    ),
  overrideRiskResult: (
    enterpriseId: number,
    canonicalRiskKey: string,
    payload: { ignored?: boolean; merge_to_key?: string | null },
    options?: ApiRequestOptions,
  ) =>
    request<{ enterprise_id: number; canonical_risk_key: string; override: { ignored?: boolean; merge_to_key?: string | null } }>(
      `/risk-analysis/${enterpriseId}/overrides/${encodeURIComponent(canonicalRiskKey)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: options?.signal,
      },
    ),
  uploadDocument: async (enterpriseId: number, file: File, options?: ApiRequestOptions) => {
    const formData = new FormData();
    formData.append("enterprise_id", String(enterpriseId));
    formData.append("file", file);
    return request<{ id: number; document_name: string; parse_status: string }>(`/ingestion/documents/upload`, {
      method: "POST",
      body: formData,
      signal: options?.signal,
    });
  },
  chat: (enterpriseId: number, question: string, options?: ApiRequestOptions) =>
    request<ChatAnswerPayload>(`/chat/${enterpriseId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      signal: options?.signal,
    }),
};
