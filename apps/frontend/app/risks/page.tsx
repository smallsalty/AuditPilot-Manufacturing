"use client";

import { useEffect, useMemo, useState } from "react";
import type { RiskResultPayload } from "@auditpilot/shared-types";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { RiskTable } from "@/components/risk-table";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import { formatCacheState, getFinancialAnalysisLabel } from "@/lib/display-labels";
import {
  useDashboardResource,
  useFinancialAnalysisResource,
  useReadinessResource,
  useRiskResultsResource,
} from "@/lib/enterprise-resources";

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

export default function RisksPage() {
  const { currentEnterprise, currentEnterpriseId, enterpriseError, invalidateEnterpriseResources, setCachedResource } =
    useEnterpriseContext();
  const { data: readiness, loading: readinessLoading, error: readinessError, refresh: refreshReadiness } =
    useReadinessResource(currentEnterpriseId);
  const { data: dashboard, loading: dashboardLoading, error: dashboardError, refresh: refreshDashboard } =
    useDashboardResource(currentEnterpriseId);
  const { data: risks, loading: risksLoading, error: risksError, refresh: refreshRisks } =
    useRiskResultsResource(currentEnterpriseId);
  const {
    data: financialAnalysis,
    loading: financialAnalysisLoading,
    refresh: refreshFinancialAnalysis,
  } = useFinancialAnalysisResource(currentEnterpriseId);

  const [running, setRunning] = useState(false);
  const [displayRisks, setDisplayRisks] = useState<RiskResultPayload[]>([]);
  const [actionMessage, setActionMessage] = useState("请选择企业并准备官方文档。");

  useEffect(() => {
    setDisplayRisks([]);
  }, [currentEnterpriseId]);

  useEffect(() => {
    setDisplayRisks(risks ?? []);
  }, [risks]);

  useEffect(() => {
    if (!currentEnterpriseId) {
      setActionMessage("请先选择企业。");
      return;
    }
    if (running) {
      setActionMessage("正在执行风险分析并刷新财报专项聚合...");
      return;
    }
    if (risksLoading || readinessLoading || dashboardLoading) {
      setActionMessage("正在加载风险清单...");
      return;
    }
    if (displayRisks.length > 0) {
      setActionMessage(`当前已生成 ${displayRisks.length} 条风险项，优先展示文档证据和规则来源。`);
      return;
    }
    if (readiness?.manual_parse_required) {
      setActionMessage(`官方文档已同步，仍有 ${readiness.documents_pending_parse} 份待手动解析。`);
      return;
    }
    if (readiness && !readiness.risk_analysis_ready) {
      setActionMessage(readiness.risk_analysis_message);
      return;
    }
    setActionMessage("当前尚无风险项，可先运行风险分析或补充更多文档。");
  }, [
    currentEnterpriseId,
    dashboardLoading,
    displayRisks.length,
    readiness,
    readinessLoading,
    risksLoading,
    running,
  ]);

  const runAnalysis = async () => {
    if (!currentEnterpriseId || running || !readiness?.risk_analysis_ready) {
      return;
    }
    setRunning(true);
    try {
      await api.ingestFinancial(currentEnterpriseId);
      const result = await api.runRiskAnalysis(currentEnterpriseId);
      setDisplayRisks(result.results);
      setCachedResource("riskResults", currentEnterpriseId, result.results);
      invalidateEnterpriseResources(currentEnterpriseId, ["dashboard", "auditFocus", "readiness", "financialAnalysis"]);
      await Promise.allSettled([refreshDashboard(), refreshRisks(), refreshReadiness(), refreshFinancialAnalysis()]);
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : "风险分析运行失败。");
    } finally {
      setRunning(false);
    }
  };

  const showResults = displayRisks.length > 0;

  const pageTitle = useMemo(() => {
    if (!currentEnterprise) {
      return "风险清单与证据";
    }
    return `${currentEnterprise.name} 风险清单与证据`;
  }, [currentEnterprise]);

  return (
    <div className="space-y-6 pb-10">
      <Card>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-steel">风险清单</p>
            <h2 className="mt-3 text-3xl font-semibold text-white">{pageTitle}</h2>
            <p className="mt-2 text-haze/75">{actionMessage}</p>
            {currentEnterpriseId ? <p className="mt-3 text-sm text-haze/65">企业 ID：{currentEnterpriseId}</p> : null}
          </div>
          <Button
            onClick={() => void runAnalysis()}
            disabled={running || dashboard?.analysis_status === "running" || !currentEnterpriseId || !readiness?.risk_analysis_ready}
          >
            {running || dashboard?.analysis_status === "running" ? "分析中..." : "运行风险分析"}
          </Button>
        </div>
      </Card>

      {enterpriseError ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">{enterpriseError}</div>
        </Card>
      ) : !currentEnterpriseId ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">当前没有可用企业。</div>
        </Card>
      ) : readinessError ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">{readinessError}</div>
        </Card>
      ) : dashboardError && !showResults ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">{dashboardError}</div>
        </Card>
      ) : risksError && !showResults ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">{risksError}</div>
        </Card>
      ) : dashboardLoading || risksLoading ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">正在加载风险清单...</div>
        </Card>
      ) : (
        <>
          <Card>
            <p className="text-xs uppercase tracking-[0.24em] text-steel">财报专项分析</p>
            <p className="mt-2 text-sm text-haze/75">{financialAnalysis?.summary ?? "当前尚未生成财报专项聚合结果。"}</p>
            {financialAnalysis ? (
              <div className="mt-3 flex flex-wrap gap-3 text-xs text-haze/65">
                <span>最近更新时间：{formatTimestamp(financialAnalysis.updated_at)}</span>
                <span>摘要来源：{financialAnalysis.summary_mode === "llm" ? "MiniMax" : "降级摘要"}</span>
                <span>返回来源：{formatCacheState(financialAnalysis.cache_state)}</span>
                <span>{financialAnalysisLoading ? "读取中" : "已就绪"}</span>
              </div>
            ) : null}
            {financialAnalysis?.anomalies?.length ? (
              <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_0.9fr]">
                <div className="space-y-3">
                  {financialAnalysis.anomalies.slice(0, 6).map((item) => (
                    <div key={`${item.document_id}-${item.title}`} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                      <p className="font-medium text-white">{getFinancialAnalysisLabel(item.title, item.canonical_risk_key)}</p>
                      <p className="mt-2 text-sm text-haze/80">{item.summary}</p>
                      <p className="mt-2 text-xs text-haze/65">
                        {item.document_name}
                        {item.period ? ` | ${item.period}` : ""}
                        {item.metric_name ? ` | ${item.metric_name}` : ""}
                      </p>
                    </div>
                  ))}
                </div>
                <div className="space-y-4">
                  <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-steel">重点科目</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {financialAnalysis.focus_accounts.map((item) => (
                        <span key={item} className="rounded-full bg-black/10 px-3 py-1 text-xs text-haze/80">
                          {item}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    <p className="text-xs uppercase tracking-[0.2em] text-steel">建议程序</p>
                    <div className="mt-3 space-y-2 text-sm text-haze/80">
                      {financialAnalysis.recommended_procedures.map((item) => (
                        <p key={item}>{item}</p>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
                财报专项区只展示聚合后的异常、重点科目和建议程序，不重复文档明细。
              </div>
            )}
          </Card>

          {showResults ? (
            <RiskTable
              risks={displayRisks}
              enterpriseId={currentEnterpriseId}
              onChanged={async () => {
                if (!currentEnterpriseId) {
                  return;
                }
                invalidateEnterpriseResources(currentEnterpriseId, ["dashboard", "auditFocus", "riskResults"]);
                await Promise.allSettled([refreshRisks({ force: true }), refreshDashboard({ force: true })]);
              }}
            />
          ) : (
            <Card>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-haze/75">
                当前企业尚无可展示风险项。完成文档抽取后，这里会优先显示文档驱动的风险结果。
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
