const ANALYSIS_STATUS_LABELS: Record<string, string> = {
  not_started: "未开始",
  running: "分析中",
  completed: "已完成",
  succeeded: "已完成",
  partial_fallback: "回退完成",
  partial_failed: "部分完成",
  failed: "分析失败",
};

const SYNC_STATUS_LABELS: Record<string, string> = {
  never_synced: "未同步",
  pending: "待处理",
  syncing: "同步中",
  synced: "已同步",
  stored: "已入库",
  parse_queued: "待解析",
  parsed: "已解析",
  failed: "失败",
};

const PARSE_STATUS_LABELS: Record<string, string> = {
  uploaded: "已上传",
  parsing: "解析中",
  parsed: "已解析",
  failed: "解析失败",
};

const ANALYSIS_MODE_LABELS: Record<string, string> = {
  llm_primary: "模型主链",
  dual_stage_llm: "文档+财报独立分析",
  dual_stage_partial_fallback: "文档+财报部分回退",
  dual_stage_partial_failed: "文档+财报部分失败",
  hybrid_fallback: "模型+规则回退",
  partial_failed: "部分分析失败",
  skill_contract_failed: "输出格式校验失败",
  rule_only: "规则兜底",
  failed: "分析失败",
};

const ANALYSIS_GROUP_LABELS: Record<string, string> = {
  financial_analysis: "财报分析",
  announcement_events: "公告事件",
  governance: "治理结构",
  audit_opinion: "审计意见",
  internal_control: "内部控制",
};

const CACHE_STATE_LABELS: Record<string, string> = {
  fresh: "实时生成",
  cache_hit: "命中缓存",
  in_flight_reused: "复用进行中请求",
  persisted_hit: "已记录结果",
};

const SOURCE_TYPE_LABELS: Record<string, string> = {
  announcement: "公告",
  official_document: "官方文档",
  structured_result: "结构化结果",
  document_rule: "文档聚合",
  rule: "规则命中",
  model: "模型识别",
  baseline: "基线观察",
  financial_indicator: "财务指标",
  industry_signal: "行业信号",
  uploaded_document: "上传文档",
  derived_risk_result: "派生结果",
  announcement_event: "公告事件",
  penalty_event: "处罚/问询",
  financial_anomaly: "财务异常",
  document: "文档证据",
  cninfo: "巨潮资讯",
  upload: "上传文档",
  akshare: "AkShare",
  akshare_fast: "AkShare 快速同步",
};

const SOURCE_MODE_LABELS: Record<string, string> = {
  document_primary: "文档证据为主",
  document_plus_rule: "文档与规则联合支持",
  announcement_event: "公告事件支持",
  rule_only: "规则推断",
  baseline_observation: "基线观察",
  risk_analysis: "风险分析结果",
  hybrid: "混合结果",
};

const EVIDENCE_STATUS_LABELS: Record<string, string> = {
  document_supported: "文档证据支持",
  document_plus_rule: "文档+规则共同支持",
  announcement_event: "公告事件正文支持",
  rule_inferred: "规则推断，待文档验证",
  baseline_observation: "基线观察",
};

const EVIDENCE_TYPE_LABELS: Record<string, string> = {
  announcement: "公告",
  annual_report: "年报",
  penalty: "处罚",
  inquiry_letter: "问询函",
  financial_indicator: "财务指标",
  industry_signal: "行业信号",
  uploaded_document: "上传文档",
  derived_risk_result: "派生结果",
};

const RISK_LEVEL_LABELS: Record<string, string> = {
  HIGH: "高风险",
  MEDIUM: "中风险",
  LOW: "低风险",
};

const SEVERITY_LABELS: Record<string, string> = {
  high: "高",
  medium: "中",
  low: "低",
  HIGH: "高",
  MEDIUM: "中",
  LOW: "低",
};

const EVENT_TYPE_LABELS: Record<string, string> = {
  "Announcement Equity Control Pledge": "股权控制/质押",
  regulatory_litigation: "监管处罚与诉讼仲裁",
  accounting_audit: "会计差错与审计意见",
  fund_occupation_related_party_guarantee: "资金占用、关联交易与担保",
  debt_liquidity_default: "债务逾期、违约与流动性风险",
  announcement_equity_control_pledge: "股权控制/质押",
  equity_control_pledge: "股权控制/质押",
  performance_revision_impairment: "业绩修正、减值与非经常性损益",
  governance_personnel_internal_control: "治理异常、人员变动与内控事件",
  announcement_title_match: "公告标题命中",
  share_repurchase: "股份回购",
  convertible_bond: "可转债",
  executive_change: "高管变动",
  litigation: "诉讼仲裁",
  litigation_arbitration: "诉讼仲裁",
  penalty_or_inquiry: "处罚/问询",
  guarantee: "担保事项",
  related_party_transaction: "关联交易",
  audit_opinion_issue: "审计意见异常",
  internal_control_issue: "内控缺陷",
  financial_anomaly: "财务异常",
  major_contract: "重大合同",
  equity_pledge: "股权质押",
};

const DOCUMENT_TYPE_LABELS: Record<string, string> = {
  annual_report: "年度报告",
  annual_summary: "年度报告摘要",
  audit_report: "审计报告",
  internal_control_report: "内部控制报告",
  interim_report: "半年度报告",
  quarter_report: "季度报告",
  announcement_event: "公告事件",
  general: "通用文档",
};

const SOURCE_NAME_LABELS: Record<string, string> = {
  akshare: "AkShare",
  akshare_fast: "AkShare 快速同步",
  cninfo: "巨潮资讯",
  upload: "上传文档",
  "cninfo / upload": "巨潮资讯 / 上传文档",
  deepseek: "DeepSeek",
  local_cache: "本地缓存",
  manual: "手动录入",
};

const EXCHANGE_LABELS: Record<string, string> = {
  SSE: "上交所",
  SZSE: "深交所",
  BSE: "北交所",
  HKEX: "港交所",
};

const TIMELINE_ITEM_TYPE_LABELS: Record<string, string> = {
  document: "文档",
  event: "事件",
};

const STATUS_LABELS: Record<string, string> = {
  ...SYNC_STATUS_LABELS,
  ...PARSE_STATUS_LABELS,
  ...ANALYSIS_STATUS_LABELS,
};

const CANONICAL_RISK_LABELS: Record<string, string> = {
  revenue_recognition: "收入确认与收入真实性风险",
  receivable_recoverability: "应收账款回收与收入真实性风险",
  inventory_impairment: "存货减值与积压风险",
  cashflow_quality: "经营现金流与利润质量风险",
  related_party_transaction: "关联交易与资金占用风险",
  related_party_funds_occupation: "关联交易与资金占用风险",
  litigation_compliance: "诉讼处罚与合规风险",
  internal_control_effectiveness: "内部控制有效性风险",
  audit_opinion_issue: "审计意见异常风险",
  going_concern: "持续经营与审计意见风险",
  financing_pressure: "融资与资金压力风险",
  tax_effective_rate_anomaly: "企业所得税有效税率异常风险",
  tax_cashflow_mismatch: "税费现金流匹配异常风险",
  deferred_tax_volatility: "递延所得税波动风险",
  tax_payable_accrual: "应交税费挂账异常风险",
  announcement_regulatory_litigation: "公告监管处罚与诉讼仲裁风险",
  announcement_accounting_audit: "公告会计差错与审计意见风险",
  announcement_related_party_guarantee: "公告资金占用、关联交易与担保风险",
  announcement_debt_liquidity: "公告债务逾期与流动性风险",
  announcement_equity_control_pledge: "公告股权变动与控制权风险",
  announcement_performance_revision_impairment: "公告业绩修正与减值风险",
  announcement_governance_internal_control: "公告治理异常与内控风险",
  governance_instability: "治理结构与高管稳定性风险",
  market_signal_conflict: "市场信号背离风险",
  uncategorized: "文档发现风险",
  baseline_observation: "综合风险观察",
};

const RULE_CODE_LABELS: Record<string, string> = {
  REV_Q4_SPIKE: "收入确认风险：四季度收入占比异常偏高",
  REV_Q4_RATIO: "收入确认风险：四季度收入占比异常",
  REV_AR_GAP: "收入确认风险：应收账款增速显著高于营收增速",
  OCF_PROFIT_DIVERGENCE: "收入确认风险：经营现金流与利润背离",
  CF_PROFIT_LOW: "现金流与利润背离风险",
  INV_BACKLOG: "存货减值/积压风险：存货增速高于营收增速且周转下降",
  INV_GROWTH_TURNOVER: "存货减值/积压风险：存货增长与周转背离",
  INV_INDUSTRY_DOWN: "存货减值/积压风险：行业需求下行时存货上升",
  INV_INDUSTRY_CONFLICT: "存货减值/积压风险：企业存货与行业趋势背离",
  AR_COLLECTION: "应收账款回款风险：回款周期延长",
  AR_TURNOVER_PRESSURE: "应收账款回款风险：周转承压",
  COMPLIANCE_EVENTS: "合规与外部事件风险：诉讼处罚及负面舆情",
  OTHER_AR_ASSET_RATIO: "关联交易/资金占用风险：其他应收款占比异常",
  RELATED_PARTY_CONTROL: "关联交易/内控风险：关联结构复杂且高管频繁变动",
  Q4_PROFIT_DEVIATION: "收入确认风险：四季度利润波动异常",
  GM_EXPENSE_ANOMALY: "盈利质量风险：毛利与费用结构异常",
  EXCESS_PROFIT_INDUSTRY_OUTLIER: "超额盈利与回款质量背离风险",
  DEBT_PRESSURE_HIGH: "融资与偿债压力风险",
  TAX_ETR_ABNORMAL: "企业所得税有效税率异常风险",
  TAX_CASHFLOW_MISMATCH: "税费现金流匹配异常风险",
  DEFERRED_TAX_VOLATILITY: "递延所得税波动风险",
  TAX_PAYABLE_ACCRUAL: "应交税费挂账异常风险",
  ANNOUNCEMENT_REGULATORY_LITIGATION: "公告监管处罚与诉讼仲裁风险",
  ANNOUNCEMENT_ACCOUNTING_AUDIT: "公告会计差错与审计意见风险",
  ANNOUNCEMENT_FUND_OCCUPATION_GUARANTEE: "公告资金占用、关联交易与担保风险",
  ANNOUNCEMENT_DEBT_LIQUIDITY_DEFAULT: "公告债务逾期与流动性风险",
  ANNOUNCEMENT_EQUITY_CONTROL_PLEDGE: "公告股权变动与控制权风险",
  ANNOUNCEMENT_PERFORMANCE_IMPAIRMENT: "公告业绩修正与减值风险",
  ANNOUNCEMENT_GOVERNANCE_INTERNAL_CONTROL: "公告治理异常与内控风险",
  FIN_DATA_REVENUE_VOLATILITY: "收入波动异常",
  FIN_DATA_PROFIT_CASH_MISMATCH: "利润现金错配",
  FIN_DATA_MARGIN_DECLINE: "利润率下滑",
  FIN_DATA_LEVERAGE_PRESSURE: "杠杆压力",
  FIN_DATA_FIXED_ASSET_VOLATILITY: "固定资产异常波动",
};

export const CANONICAL_RISK_KEYS = [
  "revenue_recognition",
  "receivable_recoverability",
  "inventory_impairment",
  "cashflow_quality",
  "related_party_transaction",
  "litigation_compliance",
  "internal_control_effectiveness",
  "audit_opinion_issue",
  "going_concern",
  "financing_pressure",
  "tax_effective_rate_anomaly",
  "tax_cashflow_mismatch",
  "deferred_tax_volatility",
  "tax_payable_accrual",
  "announcement_regulatory_litigation",
  "announcement_accounting_audit",
  "announcement_related_party_guarantee",
  "announcement_debt_liquidity",
  "announcement_equity_control_pledge",
  "announcement_performance_revision_impairment",
  "announcement_governance_internal_control",
  "governance_instability",
  "market_signal_conflict",
  "uncategorized",
];

function formatMappedValue(value: string | null | undefined, labels: Record<string, string>, fallback = "--"): string {
  if (!value) {
    return fallback;
  }
  return resolveMappedLabel(value, labels) ?? formatReadableFallbackValue(value);
}

export function formatAnalysisStatus(value: string | null | undefined): string {
  return formatMappedValue(value, ANALYSIS_STATUS_LABELS);
}

export function formatSyncStatus(value: string | null | undefined): string {
  return formatMappedValue(value, SYNC_STATUS_LABELS);
}

export function formatParseStatus(value: string | null | undefined): string {
  return formatMappedValue(value, PARSE_STATUS_LABELS, "待处理");
}

export function formatAnalysisMode(value: string | null | undefined): string {
  const label = formatMappedValue(value, ANALYSIS_MODE_LABELS, "待生成");
  return isUnmappedLabel(label) ? "其他分析模式" : label;
}

export function formatAnalysisGroup(value: string | null | undefined): string {
  return formatMappedValue(value, ANALYSIS_GROUP_LABELS);
}

export function formatCacheState(value: string | null | undefined): string {
  return formatMappedValue(value, CACHE_STATE_LABELS);
}

export function formatSourceType(value: string | null | undefined): string {
  return formatMappedValue(value, SOURCE_TYPE_LABELS);
}

export function formatSourceMode(value: string | null | undefined): string {
  return formatMappedValue(value, SOURCE_MODE_LABELS);
}

export function formatEvidenceStatus(value: string | null | undefined): string {
  return formatMappedValue(value, EVIDENCE_STATUS_LABELS);
}

export function formatEvidenceType(value: string | null | undefined): string {
  return formatMappedValue(value, EVIDENCE_TYPE_LABELS);
}

export function formatRiskLevel(value: string | null | undefined): string {
  return formatMappedValue(value, RISK_LEVEL_LABELS);
}

export function formatSeverity(value: string | null | undefined): string {
  return formatMappedValue(value, SEVERITY_LABELS);
}

export function formatEventType(value: string | null | undefined): string {
  return formatMappedValue(value, EVENT_TYPE_LABELS);
}

export function formatDocumentType(value: string | null | undefined): string {
  return formatMappedValue(value, DOCUMENT_TYPE_LABELS);
}

export function formatSourceName(value: string | null | undefined): string {
  return formatMappedValue(value, SOURCE_NAME_LABELS);
}

export function formatExchange(value: string | null | undefined): string {
  return formatMappedValue(value, EXCHANGE_LABELS);
}

export function formatTimelineItemType(value: string | null | undefined): string {
  return formatMappedValue(value, TIMELINE_ITEM_TYPE_LABELS);
}

export function formatStatus(value: string | null | undefined): string {
  return formatMappedValue(value, STATUS_LABELS);
}

export function formatCanonicalRiskKey(value: string | null | undefined): string {
  const label = formatMappedValue(value, CANONICAL_RISK_LABELS);
  return isUnmappedLabel(label) ? "其他风险" : label;
}

export function formatRuleCode(value: string | null | undefined): string {
  const label = formatMappedValue(value, RULE_CODE_LABELS);
  if (!isUnmappedLabel(label)) return label;
  const canonicalLabel = formatMappedValue(value, CANONICAL_RISK_LABELS);
  return isUnmappedLabel(canonicalLabel) ? "其他规则" : canonicalLabel;
}

const KNOWN_LABEL_GROUPS: Array<Record<string, string>> = [
  EVENT_TYPE_LABELS,
  CANONICAL_RISK_LABELS,
  RULE_CODE_LABELS,
  SOURCE_TYPE_LABELS,
  SOURCE_MODE_LABELS,
  EVIDENCE_TYPE_LABELS,
  DOCUMENT_TYPE_LABELS,
  SOURCE_NAME_LABELS,
  ANALYSIS_STATUS_LABELS,
  ANALYSIS_MODE_LABELS,
];

function normalizeLabelKey(value: string): string {
  return value.trim().toLowerCase().replace(/[\s_-]+/g, "_");
}

function resolveMappedLabel(value: string, labels: Record<string, string>): string | null {
  if (value in labels) {
    return labels[value];
  }
  const normalized = normalizeLabelKey(value);
  for (const [key, label] of Object.entries(labels)) {
    if (normalizeLabelKey(key) === normalized) {
      return label;
    }
  }
  return null;
}

function formatReadableFallbackValue(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return "--";
  }
  if (/[\u3400-\u9fff]/.test(trimmed)) {
    return trimmed;
  }
  const normalized = trimmed.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "未映射项";
  }
  return "未映射项目";
}

function resolveKnownLabel(value: string): string | null {
  for (const labels of KNOWN_LABEL_GROUPS) {
    const matched = resolveMappedLabel(value, labels);
    if (matched) {
      return matched;
    }
  }
  return null;
}

export function formatKnownLabel(value: string | null | undefined, fallback = "--"): string {
  if (!value) {
    return fallback;
  }
  return resolveKnownLabel(value) ?? formatReadableFallbackValue(value);
}

export function isUnmappedLabel(value: string | null | undefined): boolean {
  return !value || value === "--" || value === "未映射项" || value === "未映射项目";
}

export function getFinancialAnalysisLabel(...values: Array<string | null | undefined>): string {
  for (const value of values) {
    if (!value) {
      continue;
    }
    const matched = resolveKnownLabel(value);
    if (matched) {
      return matched;
    }
  }
  const firstValue = values.find((value): value is string => Boolean(value?.trim()));
  const fallbackLabel = firstValue ? formatReadableFallbackValue(firstValue) : "--";
  return isUnmappedLabel(fallbackLabel) ? "其他风险" : fallbackLabel;
}

