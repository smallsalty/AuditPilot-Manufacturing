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
              "audit-subpanel w-full rounded-2xl border border-[#1d1912]/10 p-4 text-left transition-colors",
              isActive ? "border-[#e24c74]/45 bg-[#e24c74]/10" : "hover:bg-[#f8f3e8]",
            ].join(" ")}
          >
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-black text-[#15130f]">{risk.event_name}</p>
                  <Badge value={risk.risk_level.toUpperCase()} />
                  <Badge value="default" label={`${risk.risk_score} 分`} />
                  <Badge value="default" label={formatAnalysisStatus(risk.analysis_status)} />
                </div>
                <p className="text-sm font-semibold text-[#5d503b]">{risk.event_category}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs font-semibold text-[#8a7759]">
                <span>{formatDate(risk.source_date)}</span>
                {risk.source_url ? (
                  <span
                    className="cursor-pointer text-xs text-[#8f3148]"
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
              <div className="mt-3 rounded-xl border border-[#1d1912]/10 bg-[#fffdf7]/85 p-3 text-sm font-semibold leading-6 text-[#3f3628]">
                <p className="audit-label">风险点</p>
                {displayRiskPoints.length > 0 ? (
                  <div className="mt-2 text-sm text-[#3f3628]">{numberedItems(displayRiskPoints)}</div>
                ) : null}
                {auditFocus.length > 0 ? (
                  <p className="mt-2 text-xs text-[#5d503b]">审计关注：{auditFocus.join("；")}</p>
                ) : null}
                {evidenceExcerpt ? (
                  <p className="mt-2 text-xs text-[#5d503b]">正文证据：{evidenceExcerpt}</p>
                ) : null}
              </div>
            ) : (
              <div className="mt-3 rounded-xl border border-dashed border-[#d8c8aa] bg-[#f8f3e8]/70 p-3 text-sm font-semibold leading-6 text-[#6c5d45]">
                {risk.explanation}
              </div>
            )}
            <div className="mt-3 rounded-xl border border-[#1d1912]/10 bg-[#fffdf7]/85 p-3 text-sm font-semibold text-[#3f3628]">{risk.source_title}</div>
          </button>
        );
      })}
    </div>
  );
}
