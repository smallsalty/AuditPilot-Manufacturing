export type EnterpriseSummary = {
  id: number;
  name: string;
  ticker: string;
  industry_tag: string;
  report_year: number;
};

export type AnalysisStatus = "not_started" | "running" | "completed" | "failed";

export type EnterpriseSearchItem = EnterpriseSummary;

export type EnterpriseBootstrapPayload = {
  enterprise_id: number;
  created: boolean;
  name: string;
  ticker: string;
  industry_tag: string;
};

export type EnterpriseReadinessPayload = {
  enterprise_id: number;
  profile_ready: boolean;
  sync_status: "never_synced" | "syncing" | "synced" | "failed" | string;
  official_doc_count: number;
  official_event_count: number;
  risk_analysis_ready: boolean;
  risk_analysis_reason: string;
  risk_analysis_message: string;
  last_sync_at?: string | null;
  last_sync_source?: string | null;
  risk_analysis_status: AnalysisStatus | string;
  qa_ready: boolean;
};

export type DashboardPayload = {
  enterprise: EnterpriseSummary;
  score: {
    total: number;
    financial: number;
    operational: number;
    compliance: number;
  };
  analysis_status: AnalysisStatus;
  last_run_at?: string | null;
  last_error?: string | null;
  radar: { name: string; value: number }[];
  trend: { report_period: string; risk_score: number }[];
  top_risks: {
    id: number;
    risk_name: string;
    risk_level: string;
    risk_score: number;
    source_type: string;
  }[];
};

export type EnterpriseDetail = {
  id: number;
  name: string;
  ticker: string;
  report_year: number;
  industry_tag: string;
  sub_industry?: string | null;
  exchange: string;
  province?: string | null;
  city?: string | null;
  listed_date?: string | null;
  employee_count?: number | null;
  description?: string | null;
  portrait?: Record<string, unknown> | null;
  financial_metrics: {
    report_period: string;
    period_type: string;
    indicator_code: string;
    indicator_name: string;
    value: number;
    source: string;
  }[];
  external_events: {
    id: number;
    title: string;
    event_type: string;
    severity: string;
    event_date?: string | null;
    summary: string;
  }[];
};

export type EvidenceType =
  | "announcement"
  | "annual_report"
  | "penalty"
  | "inquiry_letter"
  | "financial_indicator"
  | "industry_signal"
  | "uploaded_document"
  | "derived_risk_result"
  | string;

export type RiskResultPayload = {
  id: number;
  risk_name: string;
  risk_category: string;
  risk_level: string;
  risk_score: number;
  source_type: string;
  reasons: string[];
  evidence_chain: {
    evidence_id: string;
    evidence_type: EvidenceType;
    source?: string | null;
    source_label?: string | null;
    published_at?: string | null;
    title: string;
    snippet: string;
    content: string;
    report_period?: string | null;
  }[];
  llm_summary?: string | null;
  llm_explanation?: string | Record<string, unknown> | null;
  focus_accounts: string[];
  focus_processes: string[];
  recommended_procedures: string[];
  evidence_types: string[];
};

export type AuditFocusPayload = {
  enterprise_id: number;
  analysis_status: AnalysisStatus;
  last_run_at?: string | null;
  last_error?: string | null;
  focus_accounts: string[];
  focus_processes: string[];
  recommended_procedures: string[];
  evidence_types: string[];
  recommendations: string[];
  recommendation_items?: {
    text: string;
    sources: string[];
  }[];
};

export type DocumentListItem = {
  id: number;
  document_name: string;
  document_type: string;
  parse_status: "uploaded" | "parsing" | "parsed" | "failed" | string;
  source: string;
  created_at?: string | null;
};

export type ChatAnswerPayload = {
  answer: string;
  basis_level: "official_document" | "structured_result" | "insufficient_context" | string;
  citations: {
    title: string;
    content: string;
    source_type: string;
  }[];
  suggested_actions: string[];
};

export type EnterpriseContextState = {
  currentEnterpriseId: number | null;
  currentEnterprise: EnterpriseSummary | null;
  enterpriseOptions: EnterpriseSearchItem[];
  searchKeyword: string;
  enterpriseLoading: boolean;
  enterpriseError?: string | null;
};

export type AuditProfilePayload = {
  company: {
    id: number;
    name: string;
    ticker: string;
    industry_tag: string;
    exchange: string;
    report_year: number;
    province?: string | null;
    city?: string | null;
    listed_date?: string | null;
    description?: string | null;
  };
  sync_status: string;
  source_priority: number;
  is_official_source: boolean;
  latest_sync_at?: string | null;
  document_count: number;
  penalty_count: number;
  latest_document_date?: string | null;
  latest_penalty_date?: string | null;
  data_sources?: {
    profile: string;
    documents: string;
    events: string;
    risk_analysis_status: string;
  };
};

export type AuditTimelineItem = {
  id: string;
  item_type: "document" | "event" | string;
  title: string;
  date?: string | null;
  source: string;
  status: string;
  summary: string;
  source_url?: string | null;
  document_type?: string | null;
  event_type?: string | null;
  severity?: string | null;
  is_official_source?: boolean;
};

export type RiskSummaryPayload = {
  document_count: number;
  penalty_count: number;
  official_document_count: number;
  high_severity_penalty_count: number;
  sync_status: string;
  highlights: string[];
  document_breakdown: Record<string, number>;
  severity_breakdown: Record<string, number>;
};

export type SyncCompanyPayload = {
  enterprise_id: number;
  sources: string[];
  company_profile_updated: boolean;
  announcements_fetched: number;
  documents_found: number;
  documents_inserted: number;
  events_found: number;
  events_inserted: number;
  parse_queued: number;
  warnings: string[];
  errors: string[];
};
