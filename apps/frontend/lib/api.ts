import type {
  AuditFocusPayload,
  ChatAnswerPayload,
  DashboardPayload,
  EnterpriseDetail,
  EnterpriseSummary,
  RiskResultPayload,
} from "@auditpilot/shared-types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  try {
    const response = await fetch(`${API_BASE_URL}/api${path}`, {
      ...init,
      cache: "no-store",
    });
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || "请求失败");
    }
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error("后端 API 不可访问，请检查 NEXT_PUBLIC_API_BASE_URL、后端服务和网络连接。");
    }
    throw error;
  }
}

export const api = {
  listEnterprises: () => request<EnterpriseSummary[]>("/enterprises"),
  getEnterprise: (enterpriseId: number) => request<EnterpriseDetail>(`/enterprises/${enterpriseId}`),
  getDashboard: (enterpriseId: number) => request<DashboardPayload>(`/enterprises/${enterpriseId}/dashboard`),
  runRiskAnalysis: (enterpriseId: number) =>
    request<{ run: { run_id: number; status: string; summary: string }; results: RiskResultPayload[] }>(
      `/risk-analysis/${enterpriseId}/run`,
      { method: "POST" },
    ),
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
    const response = await fetch(`${API_BASE_URL}/api/ingestion/documents/upload`, {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return response.json();
  },
  chat: (enterpriseId: number, question: string) =>
    request<ChatAnswerPayload>(`/chat/${enterpriseId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    }),
};
