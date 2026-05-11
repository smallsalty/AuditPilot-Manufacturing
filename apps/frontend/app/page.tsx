"use client";

import type { ReactNode } from "react";
import type { RiskResultPayload } from "@auditpilot/shared-types";

import { AuditHero } from "@/components/audit-hero";
import { useEnterpriseContext } from "@/components/enterprise-provider";
import { EChart } from "@/components/echart";
import { StatCard } from "@/components/stat-card";
import { buildRadarOption, buildTrendOption, getSafeTopRisks } from "@/lib/dashboard";
import { formatRiskLevel, formatSourceType } from "@/lib/display-labels";
import { useDashboardResource, useReadinessResource, useRiskResultsResource } from "@/lib/enterprise-resources";

function OverviewPanel({
  eyebrow,
  title,
  meta,
  summary,
  children,
}: {
  eyebrow: string;
  title: string;
  meta?: string;
  summary: string;
  children: ReactNode;
}) {
  return (
    <section className="audit-overview-panel relative overflow-hidden rounded-[28px] border border-[#1d1912]/10 px-6 py-6 text-[#15130f] shadow-[0_20px_55px_rgba(21,19,15,0.08)]">
      <div className="relative z-10 flex flex-col gap-4">
        <div className="flex flex-col gap-3 border-b border-[#1d1912]/10 pb-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="font-mono text-[0.68rem] font-semibold uppercase tracking-[0.24em] text-[#8f3148]">{eyebrow}</p>
            <h3 className="mt-2 text-[1.75rem] font-black leading-none tracking-normal text-[#15130f]">{title}</h3>
          </div>
          <div className="space-y-1 text-left lg:text-right">
            {meta ? <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#8a7759]">{meta}</p> : null}
            <p className="text-sm font-medium leading-6 text-[#5d503b]">{summary}</p>
          </div>
        </div>
        {children}
      </div>
    </section>
  );
}

function OverviewState({
  tone = "muted",
  children,
}: {
  tone?: "muted" | "error";
  children: ReactNode;
}) {
  const className =
    tone === "error"
      ? "border-[#c94b35]/25 bg-[#c94b35]/10 text-[#8c2e22]"
      : "border-[#d8c8aa] bg-[#f8f3e8]/75 text-[#6c5d45]";

  return (
    <div className={`flex h-[340px] items-center justify-center rounded-[24px] border border-dashed px-6 text-sm font-semibold ${className}`}>
      <div className="max-w-sm text-center leading-6">{children}</div>
    </div>
  );
}

function getAuditSuggestions(risk: RiskResultPayload) {
  if (risk.recommended_procedures.length > 0) {
    return risk.recommended_procedures.slice(0, 3);
  }
  if (risk.focus_accounts.length > 0) {
    return risk.focus_accounts.slice(0, 3).map((item) => `先核对${item}`);
  }
  return ["先看证据链", "再补审计程序"];
}

export default function DashboardPage() {
  const { currentEnterprise, currentEnterpriseId, enterpriseError, enterpriseLoading, enterpriseOptions } =
    useEnterpriseContext();
  const { data: readiness, loading: readinessLoading, error: readinessError } = useReadinessResource(currentEnterpriseId);
  const { data: dashboard, loading: dashboardLoading, error: dashboardError } = useDashboardResource(currentEnterpriseId);
  const { data: riskResults, loading: riskResultsLoading, error: riskResultsError } =
    useRiskResultsResource(currentEnterpriseId);

  const radarOption = buildRadarOption(dashboard?.radar);
  const trendOption = buildTrendOption(dashboard?.trend);
  const topRisks = getSafeTopRisks(dashboard);
  const riskSuggestionRows = (riskResults ?? []).slice(0, 4);
  const analysisStatus = dashboard?.analysis_status ?? readiness?.risk_analysis_status ?? "not_started";
  const dashboardMeta = [
    currentEnterprise?.ticker,
    currentEnterprise?.industry_tag,
    currentEnterprise?.report_year ? `报告年度 ${currentEnterprise.report_year}` : null,
  ]
    .filter(Boolean)
    .join(" | ");
  const radarSummary =
    analysisStatus === "completed" ? "看结构。别只看总分。" : "先跑分析。再看结构。";
  const trendSummary =
    analysisStatus === "completed" ? "分数在变。判断也该跟着变。" : "等分析落地。再看起伏。";

  return (
    <div className="space-y-6 pb-10">
      <AuditHero
        currentEnterprise={currentEnterprise}
        enterpriseCount={enterpriseOptions.length}
        enterpriseError={enterpriseError}
        enterpriseLoading={enterpriseLoading}
        readiness={readiness}
        readinessLoading={readinessLoading}
        readinessError={readinessError}
        dashboard={dashboard}
        dashboardLoading={dashboardLoading}
        dashboardError={dashboardError}
        topRisks={topRisks}
      />

      <section className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="综合风险评分" value={dashboard?.score.total ?? "--"} hint="规则与证据聚合" />
        <StatCard label="财务风险" value={dashboard?.score.financial ?? "--"} hint="收入、应收、现金流" />
        <StatCard label="经营风险" value={dashboard?.score.operational ?? "--"} hint="存货、波动、景气度" />
        <StatCard label="合规风险" value={dashboard?.score.compliance ?? "--"} hint="处罚、诉讼、内控" />
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <OverviewPanel eyebrow="风险雷达" title="风险结构画像" meta={dashboardMeta} summary={radarSummary}>
          {enterpriseError ? (
            <OverviewState tone="error">企业上下文初始化失败。</OverviewState>
          ) : dashboardError || readinessError ? (
            <OverviewState tone="error">{dashboardError ?? readinessError}</OverviewState>
          ) : dashboardLoading || readinessLoading ? (
            <OverviewState>正在加载风险画像...</OverviewState>
          ) : analysisStatus === "not_started" ? (
            <OverviewState>当前企业尚未完成风险分析。</OverviewState>
          ) : analysisStatus === "running" ? (
            <OverviewState>风险分析正在执行中...</OverviewState>
          ) : analysisStatus === "failed" ? (
            <OverviewState tone="error">{dashboard?.last_error ?? "风险分析失败，请重新运行分析。"}</OverviewState>
          ) : radarOption ? (
            <div className="audit-overview-chart h-[340px] rounded-[24px] border border-[#1d1912]/10 bg-[#fffdf7]/88 p-3">
              <EChart height={316} option={radarOption} />
            </div>
          ) : (
            <OverviewState>暂无合法雷达图数据。</OverviewState>
          )}
        </OverviewPanel>

        <OverviewPanel eyebrow="风险趋势" title="最近分析趋势" meta={dashboardMeta} summary={trendSummary}>
          {enterpriseError ? (
            <OverviewState tone="error">企业上下文初始化失败。</OverviewState>
          ) : dashboardError ? (
            <OverviewState tone="error">{dashboardError}</OverviewState>
          ) : dashboardLoading ? (
            <OverviewState>正在加载趋势数据...</OverviewState>
          ) : analysisStatus !== "completed" ? (
            <OverviewState>当前暂无可展示的趋势数据。</OverviewState>
          ) : trendOption ? (
            <div className="audit-overview-chart h-[340px] rounded-[24px] border border-[#1d1912]/10 bg-[#fffdf7]/88 p-3">
              <EChart height={316} option={trendOption} />
            </div>
          ) : (
            <OverviewState>暂无合法趋势数据。</OverviewState>
          )}
        </OverviewPanel>
      </section>

      <section className="rounded-2xl border border-[#1d1912]/10 bg-[#fffdf7] p-6 text-[#15130f] shadow-[0_20px_55px_rgba(21,19,15,0.08)]">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="font-mono text-[0.7rem] font-semibold uppercase tracking-[0.24em] text-[#8f3148]">风险到建议</p>
            <h3 className="mt-2 text-2xl font-black tracking-normal text-[#15130f]">风险项和审计动作</h3>
          </div>
          <p className="max-w-xl text-sm font-medium leading-6 text-[#5d503b]">
            左边是风险，右边是下一步。别让结论单飞。
          </p>
        </div>

        {enterpriseError ? (
          <div className="mt-5 rounded-xl border border-[#c94b35]/25 bg-[#c94b35]/10 p-4 text-sm font-semibold text-[#8c2e22]">
            企业接不上，建议先空着。
          </div>
        ) : riskResultsLoading || dashboardLoading ? (
          <div className="mt-5 rounded-xl border border-dashed border-[#d8c8aa] bg-[#f3efe4]/70 p-4 text-sm font-semibold text-[#6c5d45]">
            正在配审计动作。
          </div>
        ) : riskSuggestionRows.length > 0 ? (
          <div className="mt-6 space-y-3">
            {riskSuggestionRows.map((risk, index) => {
              const suggestions = getAuditSuggestions(risk);
              return (
                <div
                  key={risk.id}
                  className="grid gap-4 rounded-xl border border-[#1d1912]/10 bg-[#f8f3e8] p-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(22rem,1.35fr)]"
                >
                  <div className="flex items-start gap-4">
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#15130f] font-mono text-sm font-black text-[#fffaf0]">
                      {index + 1}
                    </span>
                    <div className="min-w-0">
                      <p className="text-lg font-black leading-7 text-[#15130f]">{risk.risk_name}</p>
                      <p className="mt-1 text-sm font-semibold text-[#6c5d45]">
                        {formatRiskLevel(risk.risk_level)} / {formatSourceType(risk.source_type)}
                      </p>
                    </div>
                    <span className="ml-auto font-mono text-3xl font-black text-[#c94b35]">{risk.risk_score.toFixed(1)}</span>
                  </div>
                  <div className="relative border-l-4 border-[#e24c74] pl-5">
                    <p className="font-mono text-[0.68rem] font-bold uppercase tracking-[0.22em] text-[#8f3148]">
                      审计建议
                    </p>
                    <div className="mt-3 grid gap-2 md:grid-cols-3">
                      {suggestions.map((suggestion) => (
                        <div key={suggestion} className="rounded-lg border border-[#1d1912]/10 bg-[#fffdf7] px-3 py-2 text-sm font-semibold leading-6 text-[#3f3628]">
                          {suggestion}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : topRisks.length > 0 ? (
          <div className="mt-6 grid gap-3 lg:grid-cols-2">
            {topRisks.map((risk) => (
              <div key={risk.id} className="rounded-xl border border-[#1d1912]/10 bg-[#f8f3e8] p-4">
                <div className="flex items-center justify-between gap-4">
                  <p className="font-black text-[#15130f]">{risk.risk_name}</p>
                  <span className="font-mono text-2xl font-black text-[#c94b35]">{risk.risk_score.toFixed(1)}</span>
                </div>
                <p className="mt-3 border-l-4 border-[#e24c74] pl-3 text-sm font-semibold text-[#5d503b]">
                  打开风险清单，继续看建议。
                </p>
              </div>
            ))}
          </div>
        ) : riskResultsError ? (
          <div className="mt-5 rounded-xl border border-[#c94b35]/25 bg-[#c94b35]/10 p-4 text-sm font-semibold text-[#8c2e22]">
            风险建议没读到。
          </div>
        ) : (
          <div className="mt-5 rounded-xl border border-dashed border-[#d8c8aa] bg-[#f3efe4]/70 p-4 text-sm font-semibold text-[#6c5d45]">
            暂无高风险事项。
          </div>
        )}
      </section>
    </div>
  );
}
