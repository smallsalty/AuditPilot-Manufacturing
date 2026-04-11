import type {
  AnalysisStatus,
  AuditFocusPayload,
  AuditProfilePayload,
  AuditTimelineItem,
  ChatAnswerPayload,
  DashboardPayload,
  DocumentListItem,
  EnterpriseDetail,
  EnterpriseSearchItem,
  EnterpriseSummary,
  RiskSummaryPayload,
  RiskResultPayload,
  SyncCompanyPayload,
} from "@auditpilot/shared-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function readErrorMessage(response: Response): Promise<string> {
  const text = await response.text();
  if (!text) {
    return `请求失败（${response.status}）`;
  }
  try {
    const payload = JSON.parse(text) as { detail?: string };
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      return payload.detail.trim();
    }
  } catch {
    // Ignore JSON parse error and use raw text.
  }
  return text;
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
    if (error instanceof TypeError) {
      throw new Error("后端 API 不可访问，请检查 NEXT_PUBLIC_API_BASE_URL、后端服务和网络连接。");
    }
    throw error;
  }
}

export type RiskRunResponse = {
  run: { run_id: number; status: AnalysisStatus | string; summary: string };
  results: RiskResultPayload[];
};

export const api = {
  listEnterprises: (query?: string) =>
    request<EnterpriseSearchItem[]>(`/enterprises${query?.trim() ? `?q=${encodeURIComponent(query.trim())}` : ""}`),
  getEnterprise: (enterpriseId: number) => request<EnterpriseDetail>(`/enterprises/${enterpriseId}`),
  getDashboard: (enterpriseId: number) => request<DashboardPayload>(`/enterprises/${enterpriseId}/dashboard`),
  getAuditProfile: (enterpriseId: number) => request<AuditProfilePayload>(`/companies/${enterpriseId}/audit-profile`),
  getTimeline: (enterpriseId: number) => request<AuditTimelineItem[]>(`/companies/${enterpriseId}/timeline`),
  getRiskSummary: (enterpriseId: number) => request<RiskSummaryPayload>(`/companies/${enterpriseId}/risk-summary`),
  getEnterpriseDocuments: (enterpriseId: number) =>
    request<DocumentListItem[]>(`/enterprises/${enterpriseId}/documents`),
  syncCompany: (enterpriseId: number, sources: string[] = ["akshare_fast", "cninfo"]) =>
    request<SyncCompanyPayload>(`/sync/company`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ company_id: enterpriseId, sources }),
    }),
  runRiskAnalysis: (enterpriseId: number) => request<RiskRunResponse>(`/risk-analysis/${enterpriseId}/run`, { method: "POST" }),
  getRiskResults: (enterpriseId: number) => request<RiskResultPayload[]>(`/risk-analysis/${enterpriseId}/results`),
  getAuditFocus: (enterpriseId: number) => request<AuditFocusPayload>(`/audit-focus/${enterpriseId}`),
  getReport: (enterpriseId: number, format = "json") => request(`/reports/${enterpriseId}?format=${format}`),
  ingestFinancial: (enterpriseId: number) =>
    request(`/ingestion/financial`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enterprise_id: enterpriseId, provider: "akshare", include_quarterly: true }),
    }),
  ingestRiskEvents: (enterpriseId: number) =>
    request(`/ingestion/risk-events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enterprise_id: enterpriseId, provider: "mock" }),
    }),
  ingestMacro: (industryTag = "工程机械") =>
    request(`/ingestion/macro`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ industry_tag: industryTag }),
    }),
  parseDocument: (documentId: number) =>
    request(`/documents/${documentId}/parse`, {
      method: "POST",
    }),
  getDocumentExtracts: (documentId: number) => request(`/documents/${documentId}/extracts`),
  uploadDocument: async (enterpriseId: number, file: File) => {
    const formData = new FormData();
    formData.append("enterprise_id", String(enterpriseId));
    formData.append("file", file);
    return request<{ id: number; document_name: string; parse_status: string }>(`/ingestion/documents/upload`, {
      method: "POST",
      body: formData,
    });
  },
  chat: (enterpriseId: number, question: string) =>
    request<ChatAnswerPayload>(`/chat/${enterpriseId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    }),
};
