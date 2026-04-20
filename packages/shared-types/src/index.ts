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
  documents_pending_parse: number;
  manual_parse_required: boolean;
  official_event_count: number;
  risk_analysis_ready: boolean;
  risk_analysis_reason: string;
  risk_analysis_message: string;
  last_sync_at?: string | null;
  last_sync_source?: string | null;
  risk_analysis_status: AnalysisStatus | string;
  qa_ready: boolean;
  empty_reason?: SyncEmptyReason | null;
  last_sync_diagnostics?: SyncDiagnosticsPayload | null;
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
  canonical_risk_key?: string;
  risk_name: string;
  risk_category: string;
  risk_level: string;
  risk_score: number;
  source_type: string;
  source_mode?: "document_primary" | "document_plus_rule" | "rule_only" | "document_rule" | "risk_analysis" | "hybrid" | string;
  evidence_status?: "document_supported" | "document_plus_rule" | "rule_inferred" | string;
  confidence_level?: string;
  reasons: string[];
  summary?: string | null;
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
  evidence?: {
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
  source_rules?: string[];
  source_documents?: { document_id: number; document_name: string }[];
  source_events?: { event_type?: string; event_date?: string | null; severity?: string | null; subject?: string | null }[];
  feature_support?: { metric?: string | null; value?: number | string | null; unit?: string | null; period?: string | null }[];
  llm_summary?: string | null;
  llm_explanation?: string | Record<string, unknown> | null;
  focus_accounts: string[];
  focus_processes: string[];
  recommended_procedures: string[];
  evidence_types: string[];
  score_details?: {
    base_score?: number;
    final_score?: number;
    effective_weight?: number;
    weight_multiplier?: number;
    weight_reasons?: string[];
  } | null;
  industry_comparison?: Record<string, unknown> | null;
  is_baseline_observation?: boolean;
};

export type TaxRiskMetricPayload = {
  metric_code: string;
  metric_name: string;
  value: number;
  unit?: string | null;
  report_period: string;
};

export type TaxRiskItem = {
  rule_code: string;
  canonical_risk_key: string;
  risk_name: string;
  risk_category: string;
  risk_level: string;
  risk_score: number;
  summary: string;
  reasons: string[];
  report_period: string;
  period_type: string;
  metrics: TaxRiskMetricPayload[];
  evidence_chain: {
    type?: string;
    title: string;
    content: string;
    source?: string | null;
    report_period?: string | null;
  }[];
  focus_accounts: string[];
  focus_processes: string[];
  recommended_procedures: string[];
};

export type TaxRiskPayload = {
  enterprise_id: number;
  as_of_period?: string | null;
  evaluation_basis: "latest_annual" | "latest_report" | string;
  diagnostics: {
    evaluated_rules: string[];
    skipped_rules: {
      rule_code: string;
      reason: string;
      missing_indicators?: string[];
    }[];
    missing_indicators: string[];
  };
  tax_risks: TaxRiskItem[];
};

export type AnnouncementRiskItem = {
  event_code: string;
  event_category: string;
  event_name: string;
  source_event_id?: number | null;
  matched_keywords: string[];
  risk_level: "low" | "medium" | "high" | string;
  risk_score: number;
  summary?: string | null;
  explanation: string;
  body_analysis_summary?: string | null;
  event_analysis?: AnnouncementEventAnalysis | null;
  audit_focus?: string[];
  analysis_status?: "analyzed" | "pending" | "missing" | string;
  risk_points?: string[];
  evidence_excerpt?: string | null;
  source_title: string;
  source_date?: string | null;
  source_url?: string | null;
  canonical_risk_key?: string;
  risk_category?: string;
};

export type AnnouncementRiskCategoryBreakdown = {
  event_category: string;
  count: number;
  high_risk_count: number;
  score: number;
};

export type AnnouncementEventAnalysis = {
  summary?: string | null;
  key_facts?: string[];
  risk_points?: string[];
  audit_focus?: string[];
  involved_parties?: string[];
  amounts?: string[];
  dates?: string[];
  evidence_excerpt?: string | null;
  severity?: string | null;
  confidence?: number | null;
  body_source_kind?: string | null;
  category_code?: string | null;
  prompt_template?: string | null;
  analysis_status?: string | null;
};

export type EnterpriseEventItem = {
  id: number;
  title: string;
  event_type: string;
  severity: string;
  event_date?: string | null;
  summary: string;
  source_url?: string | null;
  sync_status?: string | null;
  title_matches: Array<{
    category_code: string;
    category_name: string;
    matched_keywords: string[];
    title: string;
  }>;
  primary_title_match?: Record<string, unknown> | null;
  event_analysis?: AnnouncementEventAnalysis | null;
  event_analysis_status?: string | null;
};

export type EnterpriseEventsRiskSummary = {
  announcement_risks: AnnouncementRiskItem[];
  announcement_risk_score: number;
  announcement_risk_level: "low" | "medium" | "high" | string;
  matched_event_count: number;
  high_risk_event_count: number;
  category_breakdown: AnnouncementRiskCategoryBreakdown[];
  summary: string;
};

export type EnterpriseEventsPayload = {
  enterprise_id: number;
  risk_summary: EnterpriseEventsRiskSummary;
  raw_events: EnterpriseEventItem[];
};

export type AnnouncementRiskSummary = {
  announcement_risks: AnnouncementRiskItem[];
  announcement_risk_score: number;
  announcement_risk_level: "low" | "medium" | "high" | string;
  matched_event_count: number;
  high_risk_event_count: number;
  category_breakdown: AnnouncementRiskCategoryBreakdown[];
  announcement_summary: string;
};

export type AuditFocusPayload = {
  enterprise_id: number;
  analysis_status: AnalysisStatus;
  last_run_at?: string | null;
  last_error?: string | null;
  cache_state?: "persisted_hit" | "generated" | "fallback" | string;
  focus_accounts: string[];
  focus_processes: string[];
  recommended_procedures: string[];
  evidence_types: string[];
  recommendations: string[];
  recommendation_items?: {
    text: string;
    sources: string[];
    rationale?: string;
  }[];
  items?: {
    id: string;
    title: string;
    summary: string;
    targeted_advice?: string;
    rationale?: string;
    cache_state?: "persisted_hit" | "generated" | "fallback" | string;
    sources: string[];
    evidence_preview?: string[];
    expanded_sections?: {
      title: string;
      items: string[];
    }[];
  }[];
};

export type RiskAnalysisRunPayload = {
  run: {
    run_id: number;
    status: AnalysisStatus | string;
    summary: string;
  };
  results: RiskResultPayload[];
  announcement_risks: AnnouncementRiskItem[];
  announcement_risk_score: number;
  announcement_risk_level: "low" | "medium" | "high" | string;
  matched_event_count: number;
  high_risk_event_count: number;
  category_breakdown: AnnouncementRiskCategoryBreakdown[];
  announcement_summary?: string | null;
  audit_focus?: AuditFocusPayload | null;
};

export type DocumentListItem = {
  id: number;
  document_name: string;
  document_type: string;
  classified_type?: string | null;
  parse_status: "uploaded" | "parsing" | "parsed" | "failed" | string;
  source: string;
  supports_deep_dive?: boolean;
  extract_status?: "ready" | "failed" | "pending" | string;
  extract_family_summary?: string[];
  event_coverage?: string[];
  latest_extract_version?: string | null;
  analysis_status?: "pending" | "running" | "succeeded" | "partial_fallback" | "failed" | string;
  analysis_mode?: "llm_primary" | "hybrid_fallback" | "rule_only" | string | null;
  analysis_version?: string | null;
  analyzed_at?: string | null;
  analysis_groups?: DocumentAnalysisGroup[];
  last_error_message?: string | null;
  last_error_at?: string | null;
  created_at?: string | null;
};

export type DocumentAnalysisGroup =
  | "financial_analysis"
  | "announcement_events"
  | "governance"
  | "audit_opinion"
  | "internal_control";

export type DocumentExtractItem = {
  id: number;
  extract_type: string;
  extract_version?: string | null;
  extract_family?: string | null;
  title: string;
  summary: string;
  problem_summary: string;
  parameters?: Record<string, unknown> | null;
  applied_rules: string[];
  evidence_excerpt: string;
  page_number?: number | null;
  page_start?: number | null;
  page_end?: number | null;
  section_title?: string | null;
  paragraph_hash?: string | null;
  evidence_span_id?: string | null;
  keywords?: string[] | null;
  detail_level: "general" | "financial_deep_dive" | string;
  financial_topics?: string[] | null;
  note_refs?: string[] | null;
  risk_points?: string[] | null;
  fact_tags?: string[] | null;
  metric_name?: string | null;
  metric_value?: number | null;
  metric_unit?: string | null;
  compare_target?: string | null;
  compare_value?: number | null;
  period?: string | null;
  fiscal_year?: number | null;
  fiscal_quarter?: number | null;
  event_type?: string | null;
  event_direction?: string | null;
  event_severity?: string | null;
  event_date?: string | null;
  subject?: string | null;
  amount?: number | null;
  counterparty?: string | null;
  direction?: string | null;
  severity?: string | null;
  conditions?: string | null;
  opinion_type?: string | null;
  defect_level?: string | null;
  conclusion?: string | null;
  affected_scope?: string | null;
  auditor_or_board_source?: string | null;
  canonical_risk_key?: string | null;
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

export type FinancialAnalysisDocument = {
  document_id: number;
  document_name: string;
  classified_type: string;
  period?: string | null;
  fiscal_year?: number | null;
  analysis_status?: string | null;
  analysis_mode?: string | null;
  extract_count: number;
  key_metrics: FinancialMetricPoint[];
  anomalies: FinancialAnomalyItem[];
};

export type FinancialMetricPoint = {
  document_id: number;
  document_name: string;
  metric_name: string;
  metric_value?: number | null;
  metric_unit?: string | null;
  period?: string | null;
  fiscal_year?: number | null;
};

export type FinancialAnomalyItem = {
  document_id: number;
  document_name: string;
  title: string;
  summary: string;
  canonical_risk_key?: string | null;
  metric_name?: string | null;
  metric_value?: number | null;
  metric_unit?: string | null;
  period?: string | null;
  section_title?: string | null;
  page_start?: number | null;
  page_end?: number | null;
};

export type FinancialEvidenceItem = {
  document_id: number;
  document_name: string;
  title: string;
  snippet: string;
  period?: string | null;
  section_title?: string | null;
  page_start?: number | null;
  page_end?: number | null;
};

export type FinancialAnalysisPayload = {
  enterprise_id: number;
  summary: string;
  summary_mode: "llm" | "fallback";
  cached: boolean;
  cache_state: "fresh" | "cache_hit" | "in_flight_reused" | "persisted_hit";
  updated_at?: string | null;
  documents: FinancialAnalysisDocument[];
  periods: string[];
  key_metrics: FinancialMetricPoint[];
  anomalies: FinancialAnomalyItem[];
  evidence: FinancialEvidenceItem[];
  focus_accounts: string[];
  recommended_procedures: string[];
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
  other_found?: number;
  parse_queued: number;
  annual_package_attempted: boolean;
  annual_package_target_years: number[];
  annual_package_found: number;
  annual_package_inserted: number;
  empty_reason?: SyncEmptyReason | null;
  warnings: string[];
  errors: string[];
  diagnostics?: SyncDiagnosticsPayload | null;
};

export type SyncEmptyReason =
  | "no_sync_run"
  | "generic_window_no_documents"
  | "annual_package_not_published"
  | "provider_returned_only_other"
  | "provider_error";

export type SyncDiagnosticsPayload = {
  is_initial_sync: boolean;
  window_kind: string;
  date_from: string;
  date_to: string;
  initial_window: {
    date_from: string;
    date_to: string;
  };
  annual_package_attempted: boolean;
  annual_package_target_years: number[];
  annual_package_found: number;
  annual_package_inserted: number;
  empty_reason?: SyncEmptyReason | null;
  classification_counts: {
    document: number;
    penalty: number;
    other: number;
  };
};
