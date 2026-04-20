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

function formatAnalysisStatus(value?: string | null): string {
  if (value === "analyzed") {
    return "已生成正文分析";
  }
  if (value === "pending") {
    return "正文分析排队中";
  }
  return "正文分析未生成";
}

function numberedItems(items: string[]) {
  return (
    <ol className="list-decimal space-y-1 pl-4">
      {items.map((item, index) => (
        <li key={`${index}-${item}`}>{item}</li>
      ))}
    </ol>
  );
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
        const riskPoints = Array.isArray(risk.risk_points)
          ? risk.risk_points.slice(0, 3)
          : Array.isArray(risk.event_analysis?.risk_points)
            ? risk.event_analysis.risk_points.slice(0, 3)
            : [];
        const auditFocus = Array.isArray(risk.audit_focus) ? risk.audit_focus.slice(0, 3) : [];
        const evidenceExcerpt = risk.evidence_excerpt ?? risk.event_analysis?.evidence_excerpt ?? null;
        const hasAnalysis = risk.analysis_status === "analyzed" && Boolean(bodySummary);
        const displayRiskPoints = riskPoints.length > 0 ? riskPoints : bodySummary ? [bodySummary] : [];
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
                  <Badge value="default" label={formatAnalysisStatus(risk.analysis_status)} />
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
            {hasAnalysis ? (
              <div className="mt-3 rounded-lg border bg-muted/30 p-3 text-sm leading-6 text-foreground">
                <p className="text-xs font-medium text-muted-foreground">风险点</p>
                {displayRiskPoints.length > 0 ? (
                  <div className="mt-2 text-sm text-foreground">{numberedItems(displayRiskPoints)}</div>
                ) : null}
                {auditFocus.length > 0 ? (
                  <p className="mt-2 text-xs text-muted-foreground">审计关注：{auditFocus.join("；")}</p>
                ) : null}
                {evidenceExcerpt ? (
                  <p className="mt-2 text-xs text-muted-foreground">正文证据：{evidenceExcerpt}</p>
                ) : null}
              </div>
            ) : (
              <div className="mt-3 rounded-lg border border-dashed bg-muted/20 p-3 text-sm leading-6 text-muted-foreground">
                {risk.explanation}
              </div>
            )}
            <div className="mt-3 rounded-lg bg-muted/40 p-3 text-sm text-foreground">{risk.source_title}</div>
          </button>
        );
      })}
    </div>
  );
}
