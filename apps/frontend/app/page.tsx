"use client";

import Link from "next/link";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { EChart } from "@/components/echart";
import { StatCard } from "@/components/stat-card";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { buildRadarOption, buildTrendOption, getSafeTopRisks } from "@/lib/dashboard";
import { useDashboardResource } from "@/lib/enterprise-resources";

export default function DashboardPage() {
  const { currentEnterprise, currentEnterpriseId, enterpriseError, enterpriseLoading, enterpriseOptions } =
    useEnterpriseContext();
  const { data: dashboard, loading: dashboardLoading, error: dashboardError } = useDashboardResource(currentEnterpriseId);

  const radarOption = buildRadarOption(dashboard?.radar);
  const trendOption = buildTrendOption(dashboard?.trend);
  const topRisks = getSafeTopRisks(dashboard);
  const analysisStatus = dashboard?.analysis_status ?? "not_started";

  return (
    <div className="space-y-6 pb-10">
      <section className="rounded-[36px] border border-white/10 bg-white/5 p-6 shadow-soft backdrop-blur-sm">
        <div className="grid gap-6 lg:grid-cols-[1.4fr_0.8fr]">
          <div>
            <p className="text-xs uppercase tracking-[0.32em] text-steel">Audit Command Deck</p>
            <h2 className="mt-3 max-w-3xl text-4xl font-semibold leading-tight text-white">
              制造业上市公司智能风险识别与审计重点提示系统
            </h2>
            <p className="mt-4 max-w-3xl text-base text-haze/70">
              聚合结构化财务、外部风险事件、年报文本与规则库，面向审计前期风险识别形成可解释、可追问的审计智能体演示。
            </p>
          </div>
          <Card>
            <p className="text-xs uppercase tracking-[0.24em] text-steel">当前企业概况</p>
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
                    当前分析状态：{dashboard?.analysis_status ?? "not_started"}
                  </p>
                </div>
              ) : enterpriseOptions.length === 0 ? (
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-4 text-sm text-haze/75">
                  当前没有可演示企业
                </div>
              ) : (
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-4 text-sm text-haze/75">
                  请先选择企业
                </div>
              )}
            </div>
            <div className="mt-5 grid grid-cols-2 gap-3">
              <Link href="/risks">
                <Button className="w-full">查看风险</Button>
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
        <StatCard label="综合风险评分" value={dashboard?.score.total ?? "--"} hint="多维聚合" />
        <StatCard label="财务风险" value={dashboard?.score.financial ?? "--"} hint="收入/应收/现金流" />
        <StatCard label="经营风险" value={dashboard?.score.operational ?? "--"} hint="存货/景气度/异常波动" />
        <StatCard label="合规风险" value={dashboard?.score.compliance ?? "--"} hint="处罚/诉讼/内控" />
      </section>

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-steel">Risk Radar</p>
              <h3 className="mt-2 text-xl font-semibold text-white">风险雷达图</h3>
            </div>
          </div>
          {enterpriseError ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-red-400/20 bg-red-500/10 px-6 text-sm text-red-100">
              企业上下文初始化失败
            </div>
          ) : dashboardError ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-red-400/20 bg-red-500/10 px-6 text-sm text-red-100">
              总览数据加载失败
            </div>
          ) : dashboardLoading ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-6 text-sm text-haze/75">
              正在加载雷达图数据...
            </div>
          ) : analysisStatus === "not_started" ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-6 text-sm text-haze/75">
              当前企业尚未运行风险分析
            </div>
          ) : analysisStatus === "running" ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-6 text-sm text-haze/75">
              风险分析正在执行中
            </div>
          ) : analysisStatus === "failed" ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-red-400/20 bg-red-500/10 px-6 text-sm text-red-100">
              风险分析失败：{dashboard?.last_error ?? "请重试分析任务"}
            </div>
          ) : radarOption ? (
            <EChart height={340} option={radarOption} />
          ) : (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-6 text-sm text-haze/75">
              暂无合法雷达图数据
            </div>
          )}
        </Card>
        <Card>
          <p className="text-xs uppercase tracking-[0.24em] text-steel">Risk Momentum</p>
          <h3 className="mt-2 text-xl font-semibold text-white">风险趋势图</h3>
          {enterpriseError ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-red-400/20 bg-red-500/10 px-6 text-sm text-red-100">
              企业上下文初始化失败
            </div>
          ) : dashboardError ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-red-400/20 bg-red-500/10 px-6 text-sm text-red-100">
              总览数据加载失败
            </div>
          ) : dashboardLoading ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-6 text-sm text-haze/75">
              正在加载趋势图数据...
            </div>
          ) : analysisStatus === "not_started" ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-6 text-sm text-haze/75">
              当前企业尚未运行风险分析
            </div>
          ) : analysisStatus === "running" ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-6 text-sm text-haze/75">
              风险分析正在执行中
            </div>
          ) : analysisStatus === "failed" ? (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-red-400/20 bg-red-500/10 px-6 text-sm text-red-100">
              风险分析失败：{dashboard?.last_error ?? "请重试分析任务"}
            </div>
          ) : trendOption ? (
            <EChart height={340} option={trendOption} />
          ) : (
            <div className="flex h-[340px] items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-6 text-sm text-haze/75">
              暂无合法趋势数据
            </div>
          )}
        </Card>
      </section>

      <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <Card>
          <p className="text-xs uppercase tracking-[0.24em] text-steel">Top Risks</p>
          <h3 className="mt-2 text-xl font-semibold text-white">Top 风险项</h3>
          {enterpriseError ? (
            <div className="mt-4 rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">
              企业上下文初始化失败
            </div>
          ) : dashboardError ? (
            <div className="mt-4 rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">
              总览数据加载失败
            </div>
          ) : analysisStatus === "not_started" ? (
            <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
              当前企业尚未运行风险分析，暂无 Top 风险项。
            </div>
          ) : analysisStatus === "running" ? (
            <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
              风险分析正在执行中，Top 风险项生成后会自动更新。
            </div>
          ) : analysisStatus === "failed" ? (
            <div className="mt-4 rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">
              风险分析失败：{dashboard?.last_error ?? "请重试分析任务"}
            </div>
          ) : topRisks.length > 0 ? (
            <div className="mt-4 space-y-3">
              {topRisks.map((risk) => (
                <div key={risk.id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="font-medium text-white">{risk.risk_name}</p>
                      <p className="mt-1 text-sm text-haze/70">{risk.source_type}</p>
                    </div>
                    <span className="text-2xl font-semibold text-amber-300">{risk.risk_score.toFixed(1)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
              暂无合法 Top 风险数据
            </div>
          )}
        </Card>
        <Card>
          <p className="text-xs uppercase tracking-[0.24em] text-steel">Action Strip</p>
          <h3 className="mt-2 text-xl font-semibold text-white">推荐演示路径</h3>
          <div className="mt-4 grid gap-3">
            {[
              "1. 先在风险清单页执行“运行风险分析”",
              "2. 再进入审计重点页查看重点科目与程序",
              "3. 最后到 AI 问答页追问“为什么判定存货风险高”",
            ].map((text) => (
              <div key={text} className="rounded-2xl border border-white/10 bg-white/5 p-4 text-haze/80">
                {text}
              </div>
            ))}
          </div>
        </Card>
      </section>
    </div>
  );
}
