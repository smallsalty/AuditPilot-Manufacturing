export type EnterpriseSummary = {
  id: number;
  name: string;
  ticker: string;
  industry_tag: string;
  report_year: number;
};

export type DashboardPayload = {
  enterprise: EnterpriseSummary;
  score: {
    total: number;
    financial: number;
    operational: number;
    compliance: number;
  };
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

export type RiskResultPayload = {
  id: number;
  risk_name: string;
  risk_category: string;
  risk_level: string;
  risk_score: number;
  source_type: string;
  reasons: string[];
  evidence_chain: {
    type: string;
    title: string;
    content: string;
    source?: string | null;
    report_period?: string | null;
  }[];
  llm_summary?: string | null;
  llm_explanation?: string | null;
  focus_accounts: string[];
  focus_processes: string[];
  recommended_procedures: string[];
  evidence_types: string[];
};

export type AuditFocusPayload = {
  enterprise_id: number;
  focus_accounts: string[];
  focus_processes: string[];
  recommended_procedures: string[];
  evidence_types: string[];
  recommendations: string[];
};

export type ChatAnswerPayload = {
  answer: string;
  citations: {
    title: string;
    content: string;
    source_type: string;
  }[];
  suggested_actions: string[];
};

