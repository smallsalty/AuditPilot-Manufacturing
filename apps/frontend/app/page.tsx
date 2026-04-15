"use client";

import Link from "next/link";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { EChart } from "@/components/echart";
import { StatCard } from "@/components/stat-card";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { buildRadarOption, buildTrendOption, getSafeTopRisks } from "@/lib/dashboard";
import { useDashboardResource, useReadinessResource } from "@/lib/enterprise-resources";

export default function DashboardPage() {
  const { currentEnterprise, currentEnterpriseId, enterpriseError, enterpriseLoading, enterpriseOptions } =
    useEnterpriseContext();
  const { data: readiness, loading: readinessLoading, error: readinessError } = useReadinessResource(currentEnterpriseId);
  const { data: dashboard, loading: dashboardLoading, error: dashboardError } = useDashboardResource(currentEnterpriseId);

  const radarOption = buildRadarOption(dashboard?.radar);
  const trendOption = buildTrendOption(dashboard?.trend);
  const topRisks = getSafeTopRisks(dashboard);
  const analysisStatus = dashboard?.analysis_status ?? readiness?.risk_analysis_status ?? "not_started";

  return (
    <div className="space-y-6 pb-10">
      <section className="rounded-[36px] border border-white/10 bg-white/5 p-6 shadow-soft backdrop-blur-sm">
        <div className="grid gap-6 lg:grid-cols-[1.4fr_0.8fr]">
          <div>
            <p className="text-xs uppercase tracking-[0.32em] text-steel">风险总览</p>
            <h2 className="mt-3 max-w-3xl text-4xl font-semibold leading-tight text-white">
              制造业上市公司智能风险识别与审计重点提示系统
            </h2>
            <p className="mt-4 max-w-3xl text-base text-haze/70">
              系统基于企业主数据、官方公告、结构化财务指标和规则引擎，输出企业风险画像、证据链与审计重点。
            </p>
          </div>

          <Card>
            <p className="text-xs uppercase tracking-[0.24em] text-steel">当前企业</p>
            <div className="mt-4">
              {enterpriseError ? (
                <div className="rounded-2xl border border-red-400/20 bg-red-500/10 px-4 py-4 text-sm text-red-100">
                  企业列表加载失败：{enterpriseError}
                </div>
              ) : enterpriseLoading ? (
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-4 text-sm text-haze/75">
                  正在初始化企业上下文...
                </div>
              ) : currentEnterprise ? (
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-4">
                  <p className="text-lg font-semibold text-white">{currentEnterprise.name}</p>
                  <p className="mt-2 text-sm text-haze/75">
                    {currentEnterprise.ticker} | {currentEnterprise.industry_tag} | 报告年度 {currentEnterprise.report_year}
                  </p>
                  <p className="mt-3 text-sm text-haze/70">
                    官方文档 {readiness?.official_doc_count ?? 0} 份 | 同步状态 {readiness?.sync_status ?? "--"}
                  </p>
                  {readiness?.manual_parse_required ? (
                    <p className="mt-1 text-sm text-emerald-200">已同步，待手动解析：{readiness.documents_pending_parse} 份</p>
                  ) : null}
                  <p className="mt-1 text-sm text-haze/70">风险分析状态：{analysisStatus}</p>
                </div>
              ) : enterpriseOptions.length === 0 ? (
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-4 text-sm text-haze/75">
                  当前没有可展示的企业。
                </div>
              ) : (
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-4 text-sm text-haze/75">
                  请先选择企业。
                </div>
              )}
            </div>
            <div className="mt-5 grid grid-cols-2 gap-3">
              <Link href="/risks">
                <Button className="w-full">查看风险清单</Button>
              </Link>
              <Link href="/chat">
                <Button variant="outline" className="w-full">
                  进入问答
                </Button>
              </Link>
            </div>
          </Card>
        </div>
      </section>

      <section className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
        <StatCard label="综合风险评分" value={dashboard?.score.total ?? "--"} hint="规则与证据聚合" />
        <StatCard label="财务风险" value={dashboard?.score.financial ?? "--"} hint="收入、应收、现金流" />
        <StatCard label="经营风险" value={dashboard?.score.operational ?? "--"} hint="存货、波动、景气度" />
        <StatCard label="合规风险" value={dashboard?.score.compliance ?? "--"} hint="处罚、诉讼、内控" />
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <div className="mb-4">
            <p className="text-xs uppercase tracking-[0.24em] text-steel">风险雷达</p>
            <h3 className="mt-2 text-xl font-semibold text-white">风险结构画像</h3>
          </div>
          {enterpriseError ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-red-400/20 bg-red-500/10 px-6 text-sm text-red-100">
              企业上下文初始化失败。
            </div>
          ) : dashboardError || readinessError ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-red-400/20 bg-red-500/10 px-6 text-sm text-red-100">
              {dashboardError ?? readinessError}
            </div>
          ) : dashboardLoading || readinessLoading ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-6 text-sm text-haze/75">
              正在加载风险画像...
            </div>
          ) : analysisStatus === "not_started" ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-6 text-sm text-haze/75">
              当前企业尚未完成风险分析。
            </div>
          ) : analysisStatus === "running" ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-6 text-sm text-haze/75">
              风险分析正在执行中...
            </div>
          ) : analysisStatus === "failed" ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-red-400/20 bg-red-500/10 px-6 text-sm text-red-100">
              {dashboard?.last_error ?? "风险分析失败，请重新运行分析。"}
            </div>
          ) : radarOption ? (
            <EChart height={340} option={radarOption} />
          ) : (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-6 text-sm text-haze/75">
              暂无合法雷达图数据。
            </div>
          )}
        </Card>

        <Card>
          <p className="text-xs uppercase tracking-[0.24em] text-steel">风险趋势</p>
          <h3 className="mt-2 text-xl font-semibold text-white">最近分析趋势</h3>
          {enterpriseError ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-red-400/20 bg-red-500/10 px-6 text-sm text-red-100">
              企业上下文初始化失败。
            </div>
          ) : dashboardError ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-red-400/20 bg-red-500/10 px-6 text-sm text-red-100">
              {dashboardError}
            </div>
          ) : dashboardLoading ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-6 text-sm text-haze/75">
              正在加载趋势数据...
            </div>
          ) : analysisStatus !== "completed" ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-6 text-sm text-haze/75">
              当前暂无可展示的趋势数据。
            </div>
          ) : trendOption ? (
            <EChart height={340} option={trendOption} />
          ) : (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-6 text-sm text-haze/75">
              暂无合法趋势数据。
            </div>
          )}
        </Card>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <Card>
          <p className="text-xs uppercase tracking-[0.24em] text-steel">高风险事项</p>
          <h3 className="mt-2 text-xl font-semibold text-white">Top 风险项</h3>
          {enterpriseError ? (
            <div className="mt-4 rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">
              企业上下文初始化失败。
            </div>
          ) : analysisStatus !== "completed" ? (
            <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
              当前企业尚未生成可展示的风险结果。
            </div>
          ) : topRisks.length > 0 ? (
            <div className="mt-4 space-y-3">
              {topRisks.map((risk) => (
                <div key={risk.id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="font-medium text-white">{risk.risk_name}</p>
                      <p className="mt-1 text-sm text-haze/70">
                        {risk.risk_level} | {risk.source_type}
                      </p>
                    </div>
                    <span className="text-2xl font-semibold text-amber-300">{risk.risk_score.toFixed(1)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">暂无高风险事项。</div>
          )}
        </Card>

        <Card>
          <p className="text-xs uppercase tracking-[0.24em] text-steel">数据状态</p>
          <h3 className="mt-2 text-xl font-semibold text-white">当前数据来源与准备情况</h3>
          <div className="mt-4 grid gap-3 text-sm text-haze/80">
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">企业主数据来源：AkShare</div>
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">公告与处罚来源：巨潮资讯 / 上传文档</div>
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              最近同步时间：{readiness?.last_sync_at ?? "尚未同步"}
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              最近风险分析：{dashboard?.last_run_at ?? "尚未运行"}
            </div>
            {readiness?.manual_parse_required ? (
              <div className="rounded-2xl border border-emerald-300/20 bg-emerald-300/10 p-4 text-emerald-100">
                已同步，待手动解析：{readiness.documents_pending_parse} 份官方文档
              </div>
            ) : null}
          </div>
        </Card>
      </section>
    </div>
  );
}
