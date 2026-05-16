"use client";

import type { FinancialAnalysisPayload } from "@auditpilot/shared-types";

import { Badge } from "@/components/ui/badge";
import { getFinancialAnalysisLabel } from "@/lib/display-labels";
import { getLatestFinancialAnomalies } from "@/lib/risk-display";

function formatTimestamp(value?: string | null): string {
  if (!value) {
    return "暂无";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", { hour12: false });
}

function inferReportPeriod(documentName?: string | null, fallback?: string | null): string | null {
  const name = String(documentName || "");
  const year = name.match(/(20\d{2})/)?.[1];
  if (!year) {
    return fallback || null;
  }
  if (/年度报告|年报/.test(name) && !/半年度|一季度|第一季度|三季度|第三季度/.test(name)) {
    return `${year}全年`;
  }
  if (/半年度报告|半年度|半年报/.test(name)) {
    return `${year}上半年`;
  }
  if (/第一季度报告|一季度报告|第一季度|一季度/.test(name)) {
    return `${year}第一季度`;
  }
  if (/第三季度报告|三季度报告|第三季度|三季度/.test(name)) {
    return `${year}第三季度`;
  }
  return fallback || null;
}

function formatIssueTitle(metricName?: string | null, fallback?: string | null): string {
  const metric = String(metricName || "").trim();
  if (metric) {
    return `${metric}问题`;
  }
  const label = getFinancialAnalysisLabel(fallback);
  return label === "--" ? "财报指标问题" : `${label}问题`;
}

function compactSummary(value?: string | null): string {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) {
    return "当前尚未生成财报专项聚合结果。";
  }
  const parts = text
    .split(/(?<=[。；;])/)
    .map((item) => item.trim())
    .filter(Boolean);
  return (parts.length ? parts.slice(0, 3).join("") : text).slice(0, 220);
}

export function DocumentFinancialPanel({
  financialAnalysis,
  loading,
}: {
  financialAnalysis: FinancialAnalysisPayload | null;
  loading: boolean;
}) {
  const financialItems = getLatestFinancialAnomalies(financialAnalysis);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3">
        <div>
          <p className="audit-label">财报专项分析</p>
          <div className="audit-subpanel mt-3 rounded-2xl border border-[#1d1912]/10 p-4">
            <p className="audit-label">分析总结</p>
            <p className="mt-2 text-sm font-semibold leading-6 text-[#3f3628]">{compactSummary(financialAnalysis?.summary)}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 text-xs font-semibold text-[#5d503b]">
          <Badge value="default" label={`最近更新时间：${formatTimestamp(financialAnalysis?.updated_at)}`} />
          <Badge
            value="default"
            label={`摘要来源：${financialAnalysis?.summary_mode === "llm" ? "DeepSeek" : "降级摘要"}`}
          />
          <Badge value="default" label={`返回来源：${financialAnalysis?.cache_state ?? "暂无"}`} />
          <Badge value="default" label={loading ? "读取中" : "已就绪"} />
        </div>
      </div>

      {financialItems.length ? (
        <div className="space-y-3">
          {financialItems.map((item) => {
            const period = inferReportPeriod(item.document_name, item.period);
            const riskLabel = getFinancialAnalysisLabel(item.title, item.canonical_risk_key);
            return (
              <div key={`${item.document_id}-${item.title}`} className="audit-subpanel rounded-2xl border border-[#1d1912]/10 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-black text-[#15130f]">{formatIssueTitle(item.metric_name, item.title)}</p>
                  <Badge value="default" label={riskLabel} />
                  {typeof item.risk_score === "number" ? (
                    <Badge value={item.risk_level ?? "MEDIUM"} label={`评分 ${item.risk_score.toFixed(1)}`} />
                  ) : null}
                </div>
                <p className="mt-3 text-sm font-semibold leading-6 text-[#5d503b]">{item.summary}</p>
                <p className="mt-2 text-xs font-semibold text-[#8a7759]">
                  {[period, item.document_name, item.metric_name].filter(Boolean).join(" | ")}
                </p>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-[#d8c8aa] bg-[#f8f3e8]/70 p-4 text-sm font-semibold text-[#6c5d45]">
          财报专项区只展示聚合后的分析总结和指标问题，不自动展开文档明细。
        </div>
      )}
    </div>
  );
}
