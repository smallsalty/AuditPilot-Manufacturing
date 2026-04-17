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

export function DocumentFinancialPanel({
  financialAnalysis,
  loading,
}: {
  financialAnalysis: FinancialAnalysisPayload | null;
  loading: boolean;
}) {
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">财报专项分析</p>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            {financialAnalysis?.summary ?? "当前尚未生成财报专项聚合结果。"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
          <Badge value="default" label={`最近更新时间：${formatTimestamp(financialAnalysis?.updated_at)}`} />
          <Badge
            value="default"
            label={`摘要来源：${financialAnalysis?.summary_mode === "llm" ? "MiniMax" : "降级摘要"}`}
          />
          <Badge value="default" label={`返回来源：${financialAnalysis?.cache_state ?? "暂无"}`} />
          <Badge value="default" label={loading ? "读取中" : "已就绪"} />
        </div>
      </div>

      {financialAnalysis?.anomalies?.length ? (
        <div className="grid gap-4 xl:grid-cols-[1fr_0.85fr]">
          <div className="space-y-3">
            {financialAnalysis.anomalies.slice(0, 6).map((item) => (
              <div key={`${item.document_id}-${item.title}`} className="rounded-xl border bg-background p-4">
                <p className="font-medium text-foreground">
                  {getFinancialAnalysisLabel(item.title, item.canonical_risk_key)}
                </p>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.summary}</p>
                <p className="mt-2 text-xs text-muted-foreground">
                  {item.document_name}
                  {item.period ? ` | ${item.period}` : ""}
                  {item.metric_name ? ` | ${item.metric_name}` : ""}
                </p>
              </div>
            ))}
          </div>
          <div className="space-y-4">
            <div className="rounded-xl border bg-background p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">重点科目</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {financialAnalysis.focus_accounts.map((item) => (
                  <Badge key={item} value="default" label={item} />
                ))}
              </div>
            </div>
            <div className="rounded-xl border bg-background p-4">
              <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">建议程序</p>
              <div className="mt-3 space-y-2 text-sm text-muted-foreground">
                {financialAnalysis.recommended_procedures.map((item) => (
                  <p key={item}>{item}</p>
                ))}
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-dashed bg-muted/30 p-4 text-sm text-muted-foreground">
          财报专项区只展示聚合后的异常、重点科目和建议程序，不自动展开文档明细。
        </div>
      )}
    </div>
  );
}
