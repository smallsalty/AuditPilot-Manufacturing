"use client";

import Link from "next/link";
import type { DashboardPayload, EnterpriseReadinessPayload, EnterpriseSearchItem } from "@auditpilot/shared-types";

import { formatRiskLevel } from "@/lib/display-labels";

type TopRisk = DashboardPayload["top_risks"][number];

type AuditHeroProps = {
  currentEnterprise: EnterpriseSearchItem | null;
  enterpriseCount: number;
  enterpriseError: string | null | undefined;
  enterpriseLoading: boolean;
  readiness: EnterpriseReadinessPayload | null;
  readinessLoading: boolean;
  readinessError: string | null;
  dashboard: DashboardPayload | null;
  dashboardLoading: boolean;
  dashboardError: string | null;
  topRisks: TopRisk[];
};

function getShortAnalysisStatus(status?: string | null) {
  switch (status) {
    case "completed":
      return "已跑完";
    case "running":
      return "正在跑";
    case "failed":
      return "没跑通";
    case "not_started":
    case undefined:
    case null:
      return "还没跑";
    default:
      return String(status);
  }
}

function getHeroState({
  currentEnterprise,
  enterpriseCount,
  enterpriseError,
  enterpriseLoading,
  readinessLoading,
  readinessError,
  dashboardLoading,
  dashboardError,
  analysisStatus,
}: Pick<
  AuditHeroProps,
  | "currentEnterprise"
  | "enterpriseCount"
  | "enterpriseError"
  | "enterpriseLoading"
  | "readinessLoading"
  | "readinessError"
  | "dashboardLoading"
  | "dashboardError"
> & { analysisStatus: string }) {
  if (enterpriseError) {
    return "企业没接上。";
  }
  if (readinessError || dashboardError) {
    return "这次没跑通。";
  }
  if (enterpriseLoading || readinessLoading || dashboardLoading) {
    return "正在翻材料。";
  }
  if (!currentEnterprise) {
    return enterpriseCount > 0 ? "先选一家企业。" : "先引入企业。";
  }
  if (analysisStatus === "failed") {
    return "这次没跑通。";
  }
  if (analysisStatus === "running") {
    return "正在跑风险。";
  }
  if (analysisStatus === "completed") {
    return "风险已出列。";
  }
  return "材料先排队。";
}

function formatScore(value?: number) {
  return Number.isFinite(value) ? String(value) : "--";
}

export function AuditHero({
  currentEnterprise,
  enterpriseCount,
  enterpriseError,
  enterpriseLoading,
  readiness,
  readinessLoading,
  readinessError,
  dashboard,
  dashboardLoading,
  dashboardError,
  topRisks,
}: AuditHeroProps) {
  const analysisStatus = dashboard?.analysis_status ?? readiness?.risk_analysis_status ?? "not_started";
  const shortStatus = getShortAnalysisStatus(analysisStatus);
  const heroState = getHeroState({
    currentEnterprise,
    enterpriseCount,
    enterpriseError,
    enterpriseLoading,
    readinessLoading,
    readinessError,
    dashboardLoading,
    dashboardError,
    analysisStatus,
  });
  const topRisk = topRisks[0] ?? null;
  const officialDocCount = readiness?.official_doc_count ?? 0;
  const pendingParseCount = readiness?.documents_pending_parse ?? 0;
  const riskScore = dashboard?.score.total;
  const sourceName = topRisk ? formatRiskLevel(topRisk.risk_level) : shortStatus;
  const sourceText = topRisk?.risk_name ?? (currentEnterprise ? "风险还没出炉。" : "先选一家企业。");

  return (
    <section className="audit-hero-noise relative isolate overflow-hidden rounded-[1.75rem] border border-[#2a2418]/15 bg-[#f3efe4] px-5 py-6 text-[#15130f] shadow-[0_30px_80px_rgba(21,19,15,0.18)] sm:px-8 sm:py-9 xl:px-12 xl:py-11">
      <div className="pointer-events-none absolute -right-24 top-10 h-72 w-72 rounded-full bg-[#e24c74]/16 blur-3xl" />
      <div className="pointer-events-none absolute bottom-0 left-1/4 h-48 w-80 -rotate-12 bg-[#d8c8aa]/35 blur-3xl" />
      <div className="relative grid min-h-[520px] gap-8 lg:grid-cols-[minmax(25rem,0.95fr)_minmax(24rem,1.05fr)] lg:items-end xl:min-h-[560px]">
        <div className="audit-hero-enter flex h-full flex-col justify-end pb-2 lg:pb-7">
          <p className="font-mono text-[0.68rem] font-semibold uppercase tracking-[0.34em] text-[#7a6d58]">
            AuditPilot
          </p>
          <h2 className="mt-8 text-[2.72rem] font-black leading-[0.98] tracking-normal text-[#15130f] sm:text-[3.9rem] xl:text-[4.05rem]">
            <span className="block whitespace-nowrap">让每一个null，</span>
            <span className="mt-2 block whitespace-nowrap">在数据之下一览无余</span>
          </h2>
          <div className="mt-7 grid max-w-[23rem] grid-cols-[1fr_0.82fr] gap-x-5 gap-y-2 text-[1.02rem] font-medium leading-7 text-[#4a4030] sm:text-[1.08rem]">
            <p>文表对齐</p>
            <p>事件联动</p>
            <p>白盒审计</p>
            <p>财税勾稽</p>
          </div>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              href="/risks"
              className="audit-hero-cta audit-hero-cta-primary rounded-full border border-[#15130f] bg-[#15130f] px-5 py-3 text-sm font-semibold text-[#fffaf0] shadow-[8px_8px_0_#e24c74] outline-none"
            >
              看风险清单
            </Link>
            <Link
              href="/documents"
              className="audit-hero-cta rounded-full border border-[#15130f]/70 bg-[#fffaf0]/45 px-5 py-3 text-sm font-semibold text-[#15130f] outline-none"
            >
              去翻文档
            </Link>
          </div>
          <p className="mt-7 max-w-[18rem] border-l-4 border-[#e24c74] pl-4 text-sm font-semibold leading-6 text-[#5d503b]">
            {heroState}
          </p>
        </div>

        <div className="audit-hero-enter audit-hero-enter-late relative min-h-[360px] lg:min-h-[500px]">
          <div className="absolute left-0 top-4 hidden h-[92%] w-px bg-[#15130f]/20 lg:block" />
          <div className="audit-hero-paper absolute right-0 top-4 w-[min(100%,34rem)] rotate-[-2.5deg] border border-[#15130f]/20 bg-[#fffaf0] p-5 shadow-[18px_22px_0_rgba(21,19,15,0.12)] sm:p-6">
            <div className="flex items-start justify-between gap-5 border-b border-[#15130f]/18 pb-4">
              <div className="min-w-0">
                <p className="font-mono text-[0.65rem] font-bold uppercase tracking-[0.32em] text-[#8f3148]">
                  当前企业
                </p>
                <h3 className="mt-3 truncate text-2xl font-black leading-tight text-[#15130f] sm:text-3xl">
                  {currentEnterprise?.name ?? "制造业审计桌面"}
                </h3>
              </div>
              <div className="shrink-0 text-right font-mono text-xs font-semibold leading-5 text-[#5d503b]">
                <p>{currentEnterprise?.ticker ?? "------"}</p>
                <p>{currentEnterprise?.report_year ?? "----"}</p>
              </div>
            </div>

            <div className="mt-6 grid grid-cols-[0.7fr_1fr] gap-5">
              <div className="border-r border-[#15130f]/15 pr-4">
                <p className="font-mono text-[0.65rem] uppercase tracking-[0.28em] text-[#7a6d58]">评分</p>
                <p className="mt-3 text-6xl font-black leading-none text-[#c94b35] sm:text-7xl">
                  {formatScore(riskScore)}
                </p>
                <p className="mt-3 text-sm font-semibold text-[#5d503b]">综合风险</p>
              </div>
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-3 border-b border-[#15130f]/12 pb-2">
                  <span className="text-sm font-semibold text-[#5d503b]">官方文档</span>
                  <span className="font-mono text-xl font-bold text-[#15130f]">{officialDocCount}</span>
                </div>
                <div className="flex items-center justify-between gap-3 border-b border-[#15130f]/12 pb-2">
                  <span className="text-sm font-semibold text-[#5d503b]">待解析</span>
                  <span className="font-mono text-xl font-bold text-[#15130f]">{pendingParseCount}</span>
                </div>
                <div className="flex items-center justify-between gap-3 border-b border-[#15130f]/12 pb-2">
                  <span className="text-sm font-semibold text-[#5d503b]">风险分析</span>
                  <span className="text-sm font-black text-[#15130f]">{shortStatus}</span>
                </div>
              </div>
            </div>

            <div className="mt-7">
              <div className="mb-3 flex items-center justify-between gap-3">
                <p className="font-mono text-[0.65rem] uppercase tracking-[0.3em] text-[#7a6d58]">风险刻度</p>
                <span className="rounded-full border border-[#c94b35]/40 bg-[#c94b35]/10 px-3 py-1 text-xs font-bold text-[#8c2e22]">
                  {sourceName}
                </span>
              </div>
              <div className="relative h-3 overflow-hidden rounded-full bg-[#d8c8aa]">
                <div
                  className="h-full rounded-full bg-[#c94b35]"
                  style={{ width: `${Math.min(Math.max(riskScore ?? 38, 18), 96)}%` }}
                />
              </div>
              <p className="mt-4 line-clamp-2 text-lg font-black leading-7 text-[#15130f]">{sourceText}</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
