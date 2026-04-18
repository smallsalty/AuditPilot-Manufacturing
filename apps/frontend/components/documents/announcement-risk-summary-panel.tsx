"use client";

import type { EnterpriseEventsRiskSummary } from "@auditpilot/shared-types";

import { Badge } from "@/components/ui/badge";

export function AnnouncementRiskSummaryPanel({
  riskSummary,
}: {
  riskSummary: EnterpriseEventsRiskSummary;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
      <div className="rounded-xl border bg-background p-4">
        <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">事件风险分</p>
        <p className="mt-3 text-3xl font-semibold text-foreground">{riskSummary.announcement_risk_score}</p>
        <p className="mt-2 text-sm text-muted-foreground">{riskSummary.summary}</p>
      </div>
      <div className="rounded-xl border bg-background p-4">
        <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">风险等级</p>
        <div className="mt-3">
          <Badge value={riskSummary.announcement_risk_level.toUpperCase()} />
        </div>
      </div>
      <div className="rounded-xl border bg-background p-4">
        <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">命中事件</p>
        <p className="mt-3 text-3xl font-semibold text-foreground">{riskSummary.matched_event_count}</p>
      </div>
      <div className="rounded-xl border bg-background p-4">
        <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">高风险事件</p>
        <p className="mt-3 text-3xl font-semibold text-foreground">{riskSummary.high_risk_event_count}</p>
      </div>
      <div className="rounded-xl border bg-background p-4">
        <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">类别分布</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {riskSummary.category_breakdown.length > 0 ? (
            riskSummary.category_breakdown.slice(0, 4).map((item) => (
              <Badge key={item.event_category} value="default" label={`${item.event_category} ${item.count}`} />
            ))
          ) : (
            <span className="text-sm text-muted-foreground">暂无命中</span>
          )}
        </div>
      </div>
    </div>
  );
}
