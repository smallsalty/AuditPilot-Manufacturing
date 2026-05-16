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
      <div className="audit-subpanel rounded-2xl border border-[#1d1912]/10 p-4">
        <p className="audit-label">事件风险分</p>
        <p className="mt-3 font-mono text-3xl font-black text-[#15130f]">{riskSummary.announcement_risk_score}</p>
        <p className="audit-copy mt-2 text-sm">{riskSummary.summary}</p>
      </div>
      <div className="audit-subpanel rounded-2xl border border-[#1d1912]/10 p-4">
        <p className="audit-label">风险等级</p>
        <div className="mt-3">
          <Badge value={riskSummary.announcement_risk_level.toUpperCase()} />
        </div>
      </div>
      <div className="audit-subpanel rounded-2xl border border-[#1d1912]/10 p-4">
        <p className="audit-label">命中事件</p>
        <p className="mt-3 font-mono text-3xl font-black text-[#15130f]">{riskSummary.matched_event_count}</p>
      </div>
      <div className="audit-subpanel rounded-2xl border border-[#1d1912]/10 p-4">
        <p className="audit-label">高风险事件</p>
        <p className="mt-3 font-mono text-3xl font-black text-[#15130f]">{riskSummary.high_risk_event_count}</p>
      </div>
      <div className="audit-subpanel rounded-2xl border border-[#1d1912]/10 p-4">
        <p className="audit-label">类别分布</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {riskSummary.category_breakdown.length > 0 ? (
            riskSummary.category_breakdown.slice(0, 4).map((item) => (
              <Badge key={item.event_category} value="default" label={`${item.event_category} ${item.count}`} />
            ))
          ) : (
            <span className="text-sm font-semibold text-[#8a7759]">暂无命中</span>
          )}
        </div>
      </div>
    </div>
  );
}
