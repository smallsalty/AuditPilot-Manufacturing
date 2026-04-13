"use client";

import { useEffect, useMemo, useState } from "react";
import type { RiskResultPayload } from "@auditpilot/shared-types";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { RiskTable } from "@/components/risk-table";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useDashboardResource, useReadinessResource, useRiskResultsResource } from "@/lib/enterprise-resources";

export default function RisksPage() {
  const { currentEnterprise, currentEnterpriseId, enterpriseError, invalidateEnterpriseResources, setCachedResource } =
    useEnterpriseContext();
  const { data: readiness, loading: readinessLoading, error: readinessError, refresh: refreshReadiness } =
    useReadinessResource(currentEnterpriseId);
  const { data: dashboard, loading: dashboardLoading, error: dashboardError, refresh: refreshDashboard } =
    useDashboardResource(currentEnterpriseId);
  const { data: risks, loading: risksLoading, error: risksError, refresh: refreshRisks } =
    useRiskResultsResource(currentEnterpriseId);

  const [running, setRunning] = useState(false);
  const [backgroundSyncing, setBackgroundSyncing] = useState(false);
  const [displayRisks, setDisplayRisks] = useState<RiskResultPayload[]>([]);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState("请先选择企业并准备官方数据。");

  useEffect(() => {
    setDisplayRisks(risks ?? []);
  }, [currentEnterpriseId, risks]);

  useEffect(() => {
    if (!currentEnterprise) {
      setActionMessage("请先选择企业。");
      return;
    }
    if (running) {
      setActionMessage("正在执行风险分析...");
      return;
    }
    if (backgroundSyncing) {
      setActionMessage("风险分析已完成，正在同步最新概览和结果。");
      return;
    }
    if (!readiness) {
      setActionMessage("正在检查企业数据就绪状态...");
      return;
    }
    if (!readiness.risk_analysis_ready) {
      setActionMessage(readiness.risk_analysis_message);
      return;
    }
    const status = dashboard?.analysis_status ?? readiness.risk_analysis_status ?? "not_started";
    if (status === "running") {
      setActionMessage("风险分析任务正在执行中，请稍后刷新。");
    } else if (status === "failed") {
      setActionMessage(dashboard?.last_error ?? "上一轮风险分析执行失败。");
    } else if (status === "completed") {
      setActionMessage(
        dashboard?.last_run_at ? `最近分析时间：${new Date(dashboard.last_run_at).toLocaleString()}` : "分析已完成。",
      );
    } else {
      setActionMessage(readiness.risk_analysis_message);
    }
  }, [backgroundSyncing, currentEnterprise, dashboard, readiness, running]);

  const runAnalysis = async () => {
    if (!currentEnterpriseId || running || !readiness?.risk_analysis_ready) {
      return;
    }
    setRunning(true);
    setBackgroundSyncing(false);
    setSyncError(null);
    setActionMessage("正在同步 AkShare 财务数据...");
    try {
      await api.ingestFinancial(currentEnterpriseId);
      const result = await api.runRiskAnalysis(currentEnterpriseId);
      setDisplayRisks(result.results);
      setCachedResource("riskResults", currentEnterpriseId, result.results);
      invalidateEnterpriseResources(currentEnterpriseId, ["dashboard", "auditFocus", "readiness"]);
      setActionMessage(result.run.summary);
      setBackgroundSyncing(true);
      void Promise.allSettled([refreshDashboard(), refreshRisks(), refreshReadiness()]).then((results) => {
        const rejected = results.find((item) => item.status === "rejected") as PromiseRejectedResult | undefined;
        if (rejected) {
          const message =
            rejected.reason instanceof Error ? rejected.reason.message : "后台同步失败，可手动刷新页面重试。";
          setSyncError(message);
        } else {
          setSyncError(null);
        }
        setBackgroundSyncing(false);
      });
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : "风险分析运行失败。");
    } finally {
      setRunning(false);
    }
  };

  const analysisStatus = dashboard?.analysis_status ?? readiness?.risk_analysis_status ?? "not_started";
  const riskList = displayRisks;
  const showEmpty =
    !enterpriseError &&
    !dashboardLoading &&
    !risksLoading &&
    analysisStatus === "completed" &&
    riskList.length === 0;
  const showInitialLoading = riskList.length === 0 && (dashboardLoading || risksLoading || readinessLoading);
  const showResults = riskList.length > 0;

  const pageTitle = useMemo(() => {
    if (!currentEnterprise) return "风险清单与证据";
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
          </div>
          <Button
            onClick={runAnalysis}
            disabled={running || analysisStatus === "running" || !currentEnterpriseId || !readiness?.risk_analysis_ready}
          >
            {running || analysisStatus === "running" ? "分析中..." : "运行风险分析"}
          </Button>
        </div>
      </Card>

      {backgroundSyncing ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
            后台正在同步最新概览和风险结果，当前表格优先展示本次分析返回的数据。
          </div>
        </Card>
      ) : null}

      {syncError ? (
        <Card>
          <div className="rounded-2xl border border-amber-400/20 bg-amber-500/10 p-4 text-sm text-amber-100">
            后台同步失败：{syncError}
          </div>
        </Card>
      ) : null}

      {enterpriseError ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">
            企业列表加载失败：{enterpriseError}
          </div>
        </Card>
      ) : !currentEnterpriseId ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">当前没有可用企业。</div>
        </Card>
      ) : readinessError && !showResults ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">
            企业状态加载失败：{readinessError}
          </div>
        </Card>
      ) : showInitialLoading ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">正在加载风险清单...</div>
        </Card>
      ) : readiness && !readiness.risk_analysis_ready ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-haze/75">
            {readiness.risk_analysis_message}
          </div>
        </Card>
      ) : dashboardError && !showResults ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">
            概览数据加载失败：{dashboardError}
          </div>
        </Card>
      ) : analysisStatus === "failed" ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-5 text-sm text-red-100">
            风险分析失败：{dashboard?.last_error ?? "请重新运行风险分析任务。"}
          </div>
        </Card>
      ) : risksError && !showResults ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-5 text-sm text-red-100">
            风险结果加载失败：{risksError}
          </div>
        </Card>
      ) : showEmpty ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-haze/75">
            当前企业已完成分析，但未生成可展示的风险条目。
          </div>
        </Card>
      ) : (
        <RiskTable risks={riskList} />
      )}
    </div>
  );
}
