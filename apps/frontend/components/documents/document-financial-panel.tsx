"use client";

import type { FinancialAnalysisPayload } from "@auditpilot/shared-types";

import { Badge } from "@/components/ui/badge";
import { getFinancialAnalysisLabel } from "@/lib/display-labels";

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
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">财报专项分析</p>
          <div className="mt-3 rounded-xl border bg-muted/30 p-4">
            <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">分析总结</p>
            <p className="mt-2 text-sm leading-6 text-foreground">{compactSummary(financialAnalysis?.summary)}</p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
          <Badge value="default" label={`最近更新时间：${formatTimestamp(financialAnalysis?.updated_at)}`} />
          <Badge
            value="default"
            label={`摘要来源：${financialAnalysis?.summary_mode === "llm" ? "DeepSeek" : "降级摘要"}`}
          />
          <Badge value="default" label={`返回来源：${financialAnalysis?.cache_state ?? "暂无"}`} />
          <Badge value="default" label={loading ? "读取中" : "已就绪"} />
        </div>
      </div>

      {financialAnalysis?.anomalies?.length ? (
        <div className="space-y-3">
          {financialAnalysis.anomalies.slice(0, 6).map((item) => {
            const period = inferReportPeriod(item.document_name, item.period);
            return (
              <div key={`${item.document_id}-${item.title}`} className="rounded-xl border bg-background p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium text-foreground">{formatIssueTitle(item.metric_name, item.title)}</p>
                  <Badge value="default" label={getFinancialAnalysisLabel(item.title, item.canonical_risk_key)} />
                </div>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.summary}</p>
                <p className="mt-2 text-xs text-muted-foreground">
                  {[period, item.document_name, item.metric_name].filter(Boolean).join(" | ")}
                </p>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed bg-muted/30 p-4 text-sm text-muted-foreground">
          财报专项区只展示聚合后的分析总结和指标问题，不自动展开文档明细。
        </div>
      )}
    </div>
  );
}
