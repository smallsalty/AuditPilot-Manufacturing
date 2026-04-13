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
  const [displayRisks, setDisplayRisks] = useState<RiskResultPayload[]>([]);
  const [actionMessage, setActionMessage] = useState("请选择企业并准备官方文档。");

  useEffect(() => {
    setDisplayRisks(risks ?? []);
  }, [currentEnterpriseId, risks]);

  useEffect(() => {
    if (!currentEnterpriseId) {
      setActionMessage("请先选择企业。");
      return;
    }
    if (running) {
      setActionMessage("正在执行风险分析并合并文档证据...");
      return;
    }
    if (risksLoading || readinessLoading) {
      setActionMessage("正在加载风险清单...");
      return;
    }
    if (displayRisks.length > 0) {
      setActionMessage(`当前已生成 ${displayRisks.length} 条风险项，优先展示文档证据和规则来源。`);
      return;
    }
    if (readiness && !readiness.risk_analysis_ready) {
      setActionMessage(readiness.risk_analysis_message);
      return;
    }
    setActionMessage("当前尚无风险项，可先运行风险分析或解析更多文档。");
  }, [currentEnterpriseId, displayRisks.length, readiness, readinessLoading, risksLoading, running]);

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
      invalidateEnterpriseResources(currentEnterpriseId, ["dashboard", "auditFocus", "readiness"]);
      await Promise.allSettled([refreshDashboard(), refreshRisks(), refreshReadiness()]);
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : "风险分析运行失败。");
    } finally {
      setRunning(false);
    }
  };

  const showResults = displayRisks.length > 0;

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
            disabled={running || dashboard?.analysis_status === "running" || !currentEnterpriseId || !readiness?.risk_analysis_ready}
          >
            {running || dashboard?.analysis_status === "running" ? "分析中..." : "运行风险分析"}
          </Button>
        </div>
      </Card>

      {enterpriseError ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">企业列表加载失败：{enterpriseError}</div>
        </Card>
      ) : !currentEnterpriseId ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">当前没有可用企业。</div>
        </Card>
      ) : readinessError ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">企业状态加载失败：{readinessError}</div>
        </Card>
      ) : dashboardError && !showResults ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">概览数据加载失败：{dashboardError}</div>
        </Card>
      ) : risksError && !showResults ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-4 text-sm text-red-100">风险结果加载失败：{risksError}</div>
        </Card>
      ) : dashboardLoading || risksLoading ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">正在加载风险清单...</div>
        </Card>
      ) : showResults ? (
        <RiskTable risks={displayRisks} />
      ) : (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-haze/75">
            当前企业尚无可展示风险项。只要完成文档抽取，风险页就会优先展示文档驱动的候选风险。
          </div>
        </Card>
      )}
    </div>
  );
}
