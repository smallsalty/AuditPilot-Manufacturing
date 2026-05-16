import type {
  FinancialAnalysisPayload,
  FinancialAnomalyItem,
  FinancialDataRiskItem,
  FinancialReportPayload,
  RiskResultPayload,
} from "@auditpilot/shared-types";

import {
  formatCanonicalRiskKey,
  formatEventType,
  formatEvidenceType,
  formatRuleCode,
  getFinancialAnalysisLabel,
  isUnmappedLabel,
} from "@/lib/display-labels";

export const UNIFIED_RISK_SOURCE_LABELS = {
  document: "文档",
  announcement: "公告",
  data: "数据",
  financial: "财报",
} as const;

export type UnifiedRiskSource = keyof typeof UNIFIED_RISK_SOURCE_LABELS;

export type UnifiedRiskEvidence = {
  id: string;
  source: UnifiedRiskSource;
  sourceLabel: string;
  sourceFile: string;
  title: string;
  rawText: string;
  meta: string[];
};

export type UnifiedRiskItem = {
  id: string;
  riskName: string;
  riskType: string;
  riskStatement: string;
  summary: string;
  riskLevel: string;
  riskScore?: number;
  sourceKinds: UnifiedRiskSource[];
  sourceLabels: string[];
  sourceFiles: string[];
  rawEvidence: UnifiedRiskEvidence[];
  evidenceChain: UnifiedRiskEvidence[];
  sourceRules: string[];
  recommendedProcedures: string[];
  canonicalRiskKey?: string;
  relatedRiskType?: string;
  operationRisk?: RiskResultPayload;
};

const SOURCE_ORDER: UnifiedRiskSource[] = ["document", "announcement", "data", "financial"];
const TECHNICAL_EVIDENCE_TITLES = new Set(["share_repurchase", "litigation", "litigation_arbitration"]);

export function compactText(value: string | null | undefined, fallback = "暂无概括。", maxLength = 180): string {
  const text = String(value || "")
    .replace(/\s+/g, " ")
    .trim();
  if (!text) {
    return fallback;
  }
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
}

export function buildUnifiedRiskItems(
  risks: RiskResultPayload[],
  financialAnalysis: FinancialAnalysisPayload | null,
  financialReport: FinancialReportPayload | null = null,
): UnifiedRiskItem[] {
  const items = risks.map(normalizeRiskResult);
  const existingFinancialDataRules = new Set(
    risks.flatMap((risk) => risk.source_rules ?? []).filter(isFinancialDataRuleCode),
  );

  (financialReport?.data_risks ?? []).forEach((risk, index) => {
    if (existingFinancialDataRules.has(risk.rule_code)) {
      return;
    }
    items.push(buildFinancialDataRiskItem(risk, index));
  });
  getLatestFinancialAnomalies(financialAnalysis).forEach((anomaly, index) => {
    items.push(buildFinancialRiskItem(anomaly, index));
  });

  return items;
}

export function getLatestFinancialAnomalies(financialAnalysis: FinancialAnalysisPayload | null): FinancialAnomalyItem[] {
  const anomalies = financialAnalysis?.anomalies ?? [];
  if (!anomalies.length) {
    return [];
  }
  const latest = anomalies.reduce((current, item) =>
    compareFinancialAnomalyRank(item, current) > 0 ? item : current,
  );
  return anomalies.filter((item) => item.document_id === latest.document_id);
}

export function buildUnifiedRiskSummary(items: UnifiedRiskItem[]): string {
  if (!items.length) {
    return "暂无风险项。";
  }
  const sourceText = unique(items.flatMap((item) => item.sourceLabels)).join("、") || "现有来源";
  const highCount = items.filter((item) => isHighRisk(item)).length;
  const topRisk = items.reduce<UnifiedRiskItem | null>((current, item) => {
    if (!current) {
      return item;
    }
    return (item.riskScore ?? -1) > (current.riskScore ?? -1) ? item : current;
  }, null);
  const topText = topRisk?.riskType || topRisk?.riskName || "主要风险";
  return `覆盖${sourceText}。共${items.length}项。高风险${highCount}项。先看${topText}。`;
}

export function isHighRisk(item: UnifiedRiskItem): boolean {
  return item.riskLevel?.toUpperCase() === "HIGH" || (item.riskScore ?? 0) >= 80;
}

function normalizeRiskResult(risk: RiskResultPayload): UnifiedRiskItem {
  const sourceKinds = inferRiskSources(risk);
  const riskType = getRiskType(risk);
  const riskStatement = getRiskStatement(risk);
  const rawEvidence = buildRiskRawEvidence(risk, sourceKinds);
  const evidenceChain = buildRiskEvidenceChain(risk, sourceKinds);

  return {
    id: `risk-${risk.id}`,
    riskName: risk.risk_name,
    riskType,
    riskStatement,
    summary: compactText(risk.summary ?? risk.llm_summary ?? riskStatement),
    riskLevel: risk.risk_level,
    riskScore: risk.risk_score,
    sourceKinds,
    sourceLabels: sourceKinds.map((source) => UNIFIED_RISK_SOURCE_LABELS[source]),
    sourceFiles: buildRiskSourceFiles(risk, sourceKinds),
    rawEvidence,
    evidenceChain,
    sourceRules: risk.source_rules ?? [],
    recommendedProcedures: risk.recommended_procedures ?? [],
    canonicalRiskKey: risk.canonical_risk_key,
    operationRisk: risk,
  };
}

function inferRiskSources(risk: RiskResultPayload): UnifiedRiskSource[] {
  const sources = new Set<UnifiedRiskSource>();
  const sourceType = String(risk.source_type || "");
  const sourceMode = String(risk.source_mode || "");
  const evidenceStatus = String(risk.evidence_status || "");
  const evidenceTypes = (risk.evidence_chain ?? []).map((item) => String(item.evidence_type || item.source || ""));

  if (
    sourceType === "event" ||
    sourceMode === "announcement_event" ||
    evidenceStatus === "announcement_event" ||
    (risk.source_events?.length ?? 0) > 0
  ) {
    sources.add("announcement");
  }

  if (
    sourceType === "financial_data" ||
    sourceType === "rule" ||
    sourceType === "model" ||
    evidenceTypes.some((type) => ["financial_indicator", "industry_signal", "derived_risk_result"].includes(type))
  ) {
    sources.add("data");
  }

  if (
    (risk.source_documents?.length ?? 0) > 0 ||
    ["document_primary", "document_plus_rule", "document_rule"].includes(sourceMode) ||
    ["document_supported", "document_plus_rule"].includes(evidenceStatus)
  ) {
    sources.add("document");
  }

  if (!sources.size) {
    sources.add("data");
  }

  return sortSources([...sources]);
}

function buildRiskSourceFiles(risk: RiskResultPayload, sourceKinds: UnifiedRiskSource[]): string[] {
  const files: string[] = [];
  if (sourceKinds.includes("document")) {
    files.push(...(risk.source_documents ?? []).map((document) => document.document_name));
  }
  if (sourceKinds.includes("announcement")) {
    files.push(
      ...(risk.source_events ?? [])
        .map((event) => event.subject || event.event_type)
        .filter((value): value is string => Boolean(value)),
    );
    if (!files.length) {
      files.push("公告");
    }
  }
  if (sourceKinds.includes("data")) {
    files.push("数据");
  }
  if (sourceKinds.includes("financial")) {
    files.push("财报");
  }
  return unique(files);
}

function buildRiskRawEvidence(risk: RiskResultPayload, sourceKinds: UnifiedRiskSource[]): UnifiedRiskEvidence[] {
  const items: UnifiedRiskEvidence[] = [];
  const hasDataEvidenceChain = (risk.evidence_chain ?? []).some((evidence) => isDataEvidenceType(evidence.evidence_type));

  if (sourceKinds.includes("data")) {
    (risk.reasons ?? []).forEach((reason, index) => {
      items.push({
        id: `${risk.id}-reason-${index}`,
        source: "data",
        sourceLabel: UNIFIED_RISK_SOURCE_LABELS.data,
        sourceFile: "数据",
        title: `数据判断 ${index + 1}`,
        rawText: reason,
        meta: [],
      });
    });

    if (!hasDataEvidenceChain) {
      (risk.feature_support ?? []).forEach((feature, index) => {
        const rawText = [
          feature.metric ? `指标：${feature.metric}` : null,
          feature.value !== undefined && feature.value !== null ? `数值：${feature.value}${feature.unit ?? ""}` : null,
          feature.period ? `期间：${feature.period}` : null,
        ]
          .filter(Boolean)
          .join("；");
        if (rawText) {
          items.push({
            id: `${risk.id}-feature-${index}`,
            source: "data",
            sourceLabel: UNIFIED_RISK_SOURCE_LABELS.data,
            sourceFile: "数据",
            title: feature.metric || `数据指标 ${index + 1}`,
            rawText,
            meta: formatEvidenceMeta(feature.period),
          });
        }
      });
    }
  }

  for (const evidence of risk.evidence_chain ?? []) {
    const source = inferEvidenceSource(evidence, risk, sourceKinds);
    const rawText = compactText(evidence.content || evidence.snippet, "", 400);
    if (!rawText) {
      continue;
    }
    const sourceFile = source === "data" ? "数据" : evidence.source_label || evidence.title || UNIFIED_RISK_SOURCE_LABELS[source];
    if (shouldHideTechnicalEvidence(evidence.title, rawText, sourceFile)) {
      continue;
    }
    items.push({
      id: `${risk.id}-${evidence.evidence_id}`,
      source,
      sourceLabel: UNIFIED_RISK_SOURCE_LABELS[source],
      sourceFile,
      title: formatEvidenceTitle(evidence.title, sourceFile),
      rawText,
      meta: formatEvidenceMeta(formatEvidenceType(evidence.evidence_type), evidence.published_at, evidence.report_period),
    });
  }

  return dedupeEvidence(items);
}

function buildRiskEvidenceChain(risk: RiskResultPayload, sourceKinds: UnifiedRiskSource[]): UnifiedRiskEvidence[] {
  const items: UnifiedRiskEvidence[] = [];
  for (const evidence of risk.evidence_chain ?? []) {
    const source = inferEvidenceSource(evidence, risk, sourceKinds);
    const rawText = compactText(evidence.snippet || evidence.content, "", 260);
    const sourceFile = source === "data" ? "数据" : evidence.source_label || evidence.title || UNIFIED_RISK_SOURCE_LABELS[source];
    if (!rawText || shouldHideTechnicalEvidence(evidence.title, rawText, sourceFile)) {
      continue;
    }
    items.push({
      id: `${risk.id}-chain-${evidence.evidence_id}`,
      source,
      sourceLabel: UNIFIED_RISK_SOURCE_LABELS[source],
      sourceFile,
      title: formatEvidenceTitle(evidence.title, sourceFile),
      rawText,
      meta: formatEvidenceMeta(formatEvidenceType(evidence.evidence_type), evidence.published_at, evidence.report_period),
    });
  }
  return dedupeEvidence(items);
}

function inferEvidenceSource(
  evidence: RiskResultPayload["evidence_chain"][number],
  risk: RiskResultPayload,
  sourceKinds: UnifiedRiskSource[],
): UnifiedRiskSource {
  const evidenceType = String(evidence.evidence_type || "");
  if (risk.source_type === "event" || sourceKinds.includes("announcement") && evidenceType === "announcement") {
    return "announcement";
  }
  if (["financial_indicator", "industry_signal", "derived_risk_result"].includes(evidenceType)) {
    return "data";
  }
  if (["uploaded_document", "annual_report", "announcement", "penalty", "inquiry_letter"].includes(evidenceType)) {
    return sourceKinds.includes("document") ? "document" : "announcement";
  }
  return sourceKinds[0] ?? "data";
}

function getRiskStatement(risk: RiskResultPayload): string {
  const firstReason = (risk.reasons ?? []).find((item) => item?.trim());
  const firstEvidence = (risk.evidence_chain ?? []).find((item) => item.snippet || item.content);
  return compactText(
    risk.summary ?? risk.llm_summary ?? firstReason ?? firstEvidence?.snippet ?? firstEvidence?.content,
    risk.risk_name,
  );
}

function getRiskType(risk: RiskResultPayload): string {
  const financialDataRule = getPrimaryFinancialDataRule(risk);
  if (risk.source_type === "financial_data" || financialDataRule) {
    return formatFinancialDataRiskType(financialDataRule, risk.risk_name);
  }
  const fallback = compactText(risk.risk_name, "其他风险", 80);
  if (!risk.canonical_risk_key) {
    return fallback;
  }
  const mapped = formatCanonicalRiskKey(risk.canonical_risk_key);
  return isUnmappedLabel(mapped) || mapped === "其他风险" ? fallback : mapped;
}

function shouldHideTechnicalEvidence(title: string | null | undefined, rawText: string, sourceFile: string): boolean {
  if (!isTechnicalEvidenceTitle(title)) {
    return false;
  }
  return isGenericReportEvidenceText(rawText) || areSameGenericReportTitle(rawText, sourceFile);
}

function formatEvidenceTitle(title: string | null | undefined, sourceFile: string): string {
  if (!isTechnicalEvidenceTitle(title)) {
    return title || "证据原文";
  }
  const mapped = formatEventType(title);
  if (isUnmappedLabel(mapped)) {
    return isGenericReportEvidenceText(sourceFile) ? "证据原文" : sourceFile;
  }
  return mapped;
}

function isTechnicalEvidenceTitle(value: string | null | undefined): boolean {
  const normalized = String(value || "").trim().toLowerCase().replace(/[\s-]+/g, "_");
  return TECHNICAL_EVIDENCE_TITLES.has(normalized);
}

function areSameGenericReportTitle(left: string, right: string): boolean {
  const leftTitle = normalizeReportTitle(left);
  const rightTitle = normalizeReportTitle(right);
  return Boolean(leftTitle && rightTitle && leftTitle === rightTitle && isGenericReportEvidenceText(left));
}

function isGenericReportEvidenceText(value: string | null | undefined): boolean {
  const compact = normalizeReportTitle(value);
  if (!compact) {
    return false;
  }
  if (/[诉讼仲裁处罚问询缺陷违规担保]/.test(compact)) {
    return false;
  }
  return /^(?:关于)?.{0,24}20\d{2}年?(?:年度|半年度|第一季度|一季度|第三季度|三季度|季度)?报告(?:摘要)?(?:的?公告)?$/.test(
    compact,
  );
}

function normalizeReportTitle(value: string | null | undefined): string {
  return String(value || "")
    .replace(/<[^>]+>/g, "")
    .replace(/[\s（）()【】[\]《》<>:：,，.。_-]+/g, "")
    .trim();
}

function buildFinancialRiskItem(anomaly: FinancialAnomalyItem, index: number): UnifiedRiskItem {
  const evidence = buildFinancialEvidence(anomaly, index);
  const riskType = getFinancialRiskType(anomaly);
  const relatedRiskType = anomaly.canonical_risk_key ? formatCanonicalRiskKey(anomaly.canonical_risk_key) : undefined;
  const riskScore = typeof anomaly.risk_score === "number" ? anomaly.risk_score : undefined;
  return {
    id: `financial-${anomaly.document_id}-${index}`,
    riskName: riskType,
    riskType,
    riskStatement: compactText(anomaly.summary, riskType),
    summary: compactText(anomaly.summary, "财报分析发现指标异常。"),
    riskLevel: normalizeFinancialRiskLevel(anomaly.risk_level, riskScore),
    riskScore,
    sourceKinds: ["financial"],
    sourceLabels: [UNIFIED_RISK_SOURCE_LABELS.financial],
    sourceFiles: [anomaly.document_name || "财报"],
    rawEvidence: [evidence],
    evidenceChain: [evidence],
    sourceRules: [],
    recommendedProcedures: [],
    canonicalRiskKey: anomaly.canonical_risk_key ?? undefined,
    relatedRiskType,
  };
}

function buildFinancialEvidence(anomaly: FinancialAnomalyItem, index: number): UnifiedRiskEvidence {
  const pageText =
    anomaly.page_start && anomaly.page_end
      ? `页码：${anomaly.page_start}-${anomaly.page_end}`
      : anomaly.page_start
        ? `页码：${anomaly.page_start}`
        : null;
  const rawText = [
    anomaly.document_name ? `原始文档：${anomaly.document_name}` : null,
    anomaly.canonical_risk_key ? `关联风险类型：${formatCanonicalRiskKey(anomaly.canonical_risk_key)}` : null,
    anomaly.metric_name ? `指标：${anomaly.metric_name}` : null,
    anomaly.metric_value !== undefined && anomaly.metric_value !== null
      ? `数值：${anomaly.metric_value}${anomaly.metric_unit ?? ""}`
      : null,
    anomaly.period ? `期间：${anomaly.period}` : null,
    typeof anomaly.risk_score === "number" ? `评分：${anomaly.risk_score.toFixed(1)}` : null,
    anomaly.summary ? `原文：${anomaly.summary}` : null,
  ]
    .filter(Boolean)
    .join("；");

  return {
    id: `financial-${anomaly.document_id}-${index}-${anomaly.title}`,
    source: "financial",
    sourceLabel: UNIFIED_RISK_SOURCE_LABELS.financial,
    sourceFile: anomaly.document_name || "财报",
    title: anomaly.title || anomaly.metric_name || "财报异常",
    rawText: rawText || anomaly.title || "财报分析发现异常。",
    meta: [anomaly.period, anomaly.section_title, pageText].filter((value): value is string => Boolean(value)),
  };
}

function getFinancialRiskType(anomaly: FinancialAnomalyItem): string {
  const directLabel = [anomaly.title, anomaly.metric_name].find((value) => /[\u3400-\u9fff]/.test(String(value || "")));
  if (directLabel) {
    return compactText(directLabel, "财报分析风险", 80);
  }
  const label = getFinancialAnalysisLabel(anomaly.canonical_risk_key);
  return isUnmappedLabel(label) ? "财报分析风险" : label;
}

function buildFinancialDataRiskItem(risk: FinancialDataRiskItem, index: number): UnifiedRiskItem {
  const evidence = buildFinancialDataRiskEvidence(risk, index);
  const riskType = formatFinancialDataRiskType(risk.rule_code, risk.risk_name);
  return {
    id: `data-${risk.rule_code}-${index}`,
    riskName: riskType,
    riskType,
    riskStatement: compactText(risk.judgment, risk.risk_name),
    summary: compactText(risk.evidence, risk.judgment || risk.risk_name),
    riskLevel: normalizeFinancialDataRiskLevel(risk.risk_level),
    riskScore: risk.risk_score,
    sourceKinds: ["data"],
    sourceLabels: [UNIFIED_RISK_SOURCE_LABELS.data],
    sourceFiles: ["数据"],
    rawEvidence: [evidence],
    evidenceChain: [evidence],
    sourceRules: [risk.rule_code],
    recommendedProcedures: [],
  };
}

function buildFinancialDataRiskEvidence(risk: FinancialDataRiskItem, index: number): UnifiedRiskEvidence {
  const periods = unique(risk.periods ?? []).join("、");
  const rawText = [
    `判断：${risk.judgment}`,
    `证据：${risk.evidence}`,
    periods ? `期间：${periods}` : null,
    `规则：${risk.rule_code}`,
    `得分：${risk.risk_score.toFixed(2)}`,
  ]
    .filter(Boolean)
    .join("；");

  return {
    id: `data-${risk.rule_code}-${index}`,
    source: "data",
    sourceLabel: UNIFIED_RISK_SOURCE_LABELS.data,
    sourceFile: "数据",
    title: risk.risk_name,
    rawText,
    meta: formatEvidenceMeta(risk.rule_code, periods),
  };
}

function isFinancialDataRuleCode(value: string | null | undefined): value is string {
  return String(value || "").toUpperCase().startsWith("FIN_DATA_");
}

function getPrimaryFinancialDataRule(risk: RiskResultPayload): string | undefined {
  return (risk.source_rules ?? []).find(isFinancialDataRuleCode);
}

function formatFinancialDataRiskType(ruleCode: string | null | undefined, fallback: string): string {
  const label = formatRuleCode(ruleCode);
  const fallbackText = compactText(fallback, "数据风险", 80);
  return isUnmappedLabel(label) || label === "其他规则"
    ? fallbackText === "文档发现风险"
      ? "数据风险"
      : fallbackText
    : label;
}

function isDataEvidenceType(value: string | null | undefined): boolean {
  return ["financial_indicator", "industry_signal", "derived_risk_result"].includes(String(value || ""));
}

function formatEvidenceMeta(...values: Array<string | null | undefined>): string[] {
  const result: string[] = [];
  const seen = new Set<string>();
  values.forEach((value) => {
    String(value || "")
      .split(/[，,、]/)
      .map((item) => item.trim())
      .filter(Boolean)
      .forEach((item) => {
        if (seen.has(item)) {
          return;
        }
        seen.add(item);
        result.push(item);
      });
  });
  return result;
}

function normalizeFinancialDataRiskLevel(value: string): string {
  const text = String(value || "").trim().toUpperCase();
  if (["HIGH", "高", "高风险"].includes(text)) {
    return "HIGH";
  }
  if (["LOW", "低", "低风险"].includes(text)) {
    return "LOW";
  }
  return "MEDIUM";
}

function normalizeFinancialRiskLevel(value: string | null | undefined, score: number | undefined): string {
  const text = String(value || "").trim().toUpperCase();
  if (["HIGH", "高", "高风险"].includes(text)) {
    return "HIGH";
  }
  if (["MEDIUM", "中", "中风险"].includes(text)) {
    return "MEDIUM";
  }
  if (["LOW", "低", "低风险"].includes(text)) {
    return "LOW";
  }
  if (typeof score === "number") {
    if (score >= 80) {
      return "HIGH";
    }
    if (score < 60) {
      return "LOW";
    }
    return "MEDIUM";
  }
  return "SPECIAL";
}

function compareFinancialAnomalyRank(left: FinancialAnomalyItem, right: FinancialAnomalyItem): number {
  const leftRank = financialAnomalyRank(left);
  const rightRank = financialAnomalyRank(right);
  for (let index = 0; index < leftRank.length; index += 1) {
    const delta = leftRank[index] - rightRank[index];
    if (delta !== 0) {
      return delta;
    }
  }
  return 0;
}

function financialAnomalyRank(item: FinancialAnomalyItem): [number, number, number, number] {
  const periodText = [item.period, item.document_report_period, item.document_name, item.title].filter(Boolean).join(" ");
  const [inferredYear, inferredQuarter] = inferFinancialPeriodRank(periodText);
  const fiscalQuarter = numberValue(item.fiscal_quarter);
  return [
    numberValue(item.fiscal_year) || inferredYear,
    Math.max(fiscalQuarter, inferredQuarter),
    dateRank(item.announcement_date),
    numberValue(item.document_id),
  ];
}

function inferFinancialPeriodRank(text: string): [number, number] {
  const year = Number(text.match(/(20\d{2})/)?.[1] ?? 0);
  if (/年度报告|年报|全年|FY/i.test(text)) {
    return [year, 5];
  }
  if (/三季|第三季度|Q3/i.test(text)) {
    return [year, 3];
  }
  if (/半年度|半年报|上半年|中报|Q2/i.test(text)) {
    return [year, 2];
  }
  if (/一季|第一季度|Q1/i.test(text)) {
    return [year, 1];
  }
  return [year, 0];
}

function dateRank(value: string | null | undefined): number {
  const digits = String(value || "").replace(/\D/g, "");
  if (digits.length >= 8) {
    return Number(digits.slice(0, 8));
  }
  return Number(digits || 0);
}

function numberValue(value: number | string | null | undefined): number {
  const number = Number(value || 0);
  return Number.isFinite(number) ? number : 0;
}

function sortSources(sources: UnifiedRiskSource[]): UnifiedRiskSource[] {
  return [...sources].sort((left, right) => SOURCE_ORDER.indexOf(left) - SOURCE_ORDER.indexOf(right));
}

function unique<T>(values: T[]): T[] {
  return values.filter((value, index, array) => Boolean(value) && array.indexOf(value) === index);
}

function dedupeEvidence(items: UnifiedRiskEvidence[]): UnifiedRiskEvidence[] {
  const seen = new Set<string>();
  const result: UnifiedRiskEvidence[] = [];
  for (const item of items) {
    const key = `${item.sourceFile}-${item.title}-${item.rawText}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    result.push(item);
  }
  return result;
}
