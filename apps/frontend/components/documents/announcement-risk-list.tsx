"use client";

import type { AnnouncementRiskItem } from "@auditpilot/shared-types";

import { Badge } from "@/components/ui/badge";

function formatDate(value?: string | null): string {
  if (!value) {
    return "暂无日期";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleDateString("zh-CN");
}

export function AnnouncementRiskList({
  risks,
  activeEventId,
  activeFallbackKey,
  onSelectRisk,
}: {
  risks: AnnouncementRiskItem[];
  activeEventId: number | null;
  activeFallbackKey: string | null;
  onSelectRisk: (risk: AnnouncementRiskItem) => void;
}) {
  return (
    <div className="space-y-3">
      {risks.map((risk) => {
        const fallbackKey = `${risk.source_title}::${risk.source_date ?? ""}`;
        const isActive =
          (risk.source_event_id != null && activeEventId === risk.source_event_id) ||
          (risk.source_event_id == null && activeFallbackKey === fallbackKey);
        const bodySummary = risk.body_analysis_summary ?? risk.event_analysis?.summary ?? null;
        const auditFocus = Array.isArray(risk.audit_focus) ? risk.audit_focus.slice(0, 3) : [];
        return (
          <button
            key={`${risk.event_code}-${risk.source_event_id ?? fallbackKey}`}
            type="button"
            onClick={() => onSelectRisk(risk)}
            className={[
              "w-full rounded-xl border bg-background p-4 text-left transition-colors",
              isActive ? "border-primary/40 bg-primary/5" : "hover:bg-muted/40",
            ].join(" ")}
          >
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-medium text-foreground">{risk.event_name}</p>
                  <Badge value={risk.risk_level.toUpperCase()} />
                  <Badge value="default" label={`${risk.risk_score} 分`} />
                </div>
                <p className="text-sm text-muted-foreground">{risk.event_category}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span>{formatDate(risk.source_date)}</span>
                {risk.source_url ? (
                  <span
                    className="cursor-pointer text-xs text-primary"
                    onClick={(event) => {
                      event.stopPropagation();
                      window.open(risk.source_url ?? undefined, "_blank", "noopener,noreferrer");
                    }}
                  >
                    查看公告
                  </span>
                ) : null}
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {risk.matched_keywords.map((keyword) => (
                <Badge key={keyword} value="default" label={keyword} />
              ))}
            </div>
            {bodySummary ? (
              <div className="mt-3 rounded-lg border bg-muted/30 p-3 text-sm leading-6 text-foreground">
                <p className="text-xs font-medium text-muted-foreground">正文分析总结</p>
                <p className="mt-1">{bodySummary}</p>
                {auditFocus.length > 0 ? (
                  <p className="mt-2 text-xs text-muted-foreground">审计关注：{auditFocus.join("；")}</p>
                ) : null}
              </div>
            ) : null}
            {risk.explanation && risk.explanation !== bodySummary ? (
              <p className="mt-3 text-sm leading-6 text-muted-foreground">{risk.explanation}</p>
            ) : null}
            <div className="mt-3 rounded-lg bg-muted/40 p-3 text-sm text-foreground">{risk.source_title}</div>
          </button>
        );
      })}
    </div>
  );
}
