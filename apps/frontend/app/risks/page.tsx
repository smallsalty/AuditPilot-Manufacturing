"use client";

import { useEffect, useMemo, useState } from "react";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { RiskTable } from "@/components/risk-table";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useDashboardResource, useRiskResultsResource } from "@/lib/enterprise-resources";

export default function RisksPage() {
  const { currentEnterprise, currentEnterpriseId, enterpriseError, invalidateEnterpriseResources, setCachedResource } =
    useEnterpriseContext();
  const { data: dashboard, loading: dashboardLoading, error: dashboardError, refresh: refreshDashboard } =
    useDashboardResource(currentEnterpriseId);
  const { data: risks, loading: risksLoading, error: risksError, refresh: refreshRisks } =
    useRiskResultsResource(currentEnterpriseId);
  const [running, setRunning] = useState(false);
  const [actionMessage, setActionMessage] = useState("请先选择企业并运行风险分析。");

  useEffect(() => {
    if (!currentEnterprise) {
      setActionMessage("请先选择企业。");
      return;
    }
    const status = dashboard?.analysis_status ?? "not_started";
    if (status === "running") {
      setActionMessage("风险分析任务正在执行中，请稍后刷新。");
    } else if (status === "failed") {
      setActionMessage(dashboard?.last_error ?? "上一次风险分析执行失败。");
    } else if (status === "completed") {
      setActionMessage(
        dashboard?.last_run_at ? `最近分析时间：${new Date(dashboard.last_run_at).toLocaleString()}` : "分析已完成。",
      );
    } else {
      setActionMessage("尚未运行分析。");
    }
  }, [currentEnterprise, dashboard]);

  const runAnalysis = async () => {
    if (!currentEnterpriseId || running) return;
    setRunning(true);
    setActionMessage("正在导入财务、风险事件和宏观数据...");
    try {
      await api.ingestFinancial(currentEnterpriseId);
      await api.ingestRiskEvents(currentEnterpriseId);
      await api.ingestMacro(currentEnterprise?.industry_tag ?? "工程机械");
      const result = await api.runRiskAnalysis(currentEnterpriseId);
      invalidateEnterpriseResources(currentEnterpriseId, ["dashboard", "riskResults", "auditFocus"]);
      setCachedResource("riskResults", currentEnterpriseId, result.results);
      await refreshDashboard();
      await refreshRisks();
      setActionMessage(result.run.summary);
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : "风险分析运行失败");
    } finally {
      setRunning(false);
    }
  };

  const analysisStatus = dashboard?.analysis_status ?? "not_started";
  const riskList = risks ?? [];
  const showEmpty =
    !enterpriseError &&
    !dashboardLoading &&
    !risksLoading &&
    analysisStatus === "completed" &&
    riskList.length === 0;

  const pageTitle = useMemo(() => {
    if (!currentEnterprise) return "风险清单与证据链";
    return `${currentEnterprise.name} 风险清单与证据链`;
  }, [currentEnterprise]);

  return (
    <div className="space-y-6 pb-10">
      <Card>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-steel">Risk Register</p>
            <h2 className="mt-3 text-3xl font-semibold text-white">{pageTitle}</h2>
            <p className="mt-2 text-haze/75">{actionMessage}</p>
          </div>
          <Button onClick={runAnalysis} disabled={running || analysisStatus === "running" || !currentEnterpriseId}>
            {running || analysisStatus === "running" ? "分析中..." : "运行风险分析"}
          </Button>
        </div>
      </Card>

      {enterpriseError ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">
            企业列表加载失败：{enterpriseError}
          </div>
        </Card>
      ) : !currentEnterpriseId ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
            当前没有可用企业，请先执行 seed 或导入企业数据。
          </div>
        </Card>
      ) : dashboardLoading || risksLoading ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
            正在加载风险清单...
          </div>
        </Card>
      ) : dashboardError ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">
            总览数据加载失败：{dashboardError}
          </div>
        </Card>
      ) : analysisStatus === "not_started" ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-haze/75">
            当前企业尚未运行风险分析，请先执行分析任务。
          </div>
        </Card>
      ) : analysisStatus === "failed" ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-5 text-sm text-red-100">
            风险分析失败：{dashboard?.last_error ?? "请重试风险分析任务。"}
          </div>
        </Card>
      ) : risksError ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-5 text-sm text-red-100">
            风险结果加载失败：{risksError}
          </div>
        </Card>
      ) : showEmpty ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-haze/75">
            当前企业已完成分析，但未生成风险清单。
          </div>
        </Card>
      ) : (
        <RiskTable risks={riskList} />
      )}
    </div>
  );
}
