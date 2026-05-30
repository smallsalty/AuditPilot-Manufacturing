"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import type { FinancialReportPayload, RiskResultPayload } from "@auditpilot/shared-types";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { RiskTable } from "@/components/risk-table";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import {
  useDashboardResource,
  useFinancialAnalysisResource,
  useReadinessResource,
  useRiskResultsResource,
} from "@/lib/enterprise-resources";
import { buildUnifiedRiskItems } from "@/lib/risk-display";

function RiskStateBox({
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
    <section className="audit-overview-panel rounded-[28px] border border-[#1d1912]/10 p-6 shadow-[0_20px_55px_rgba(21,19,15,0.08)]">
      <div className={`rounded-2xl border border-dashed px-5 py-5 text-sm font-semibold leading-6 ${className}`}>
        {children}
      </div>
    </section>
  );
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
    error: financialAnalysisError,
    refresh: refreshFinancialAnalysis,
  } = useFinancialAnalysisResource(currentEnterpriseId);

  const [running, setRunning] = useState(false);
  const [displayRisks, setDisplayRisks] = useState<RiskResultPayload[]>([]);
  const [actionMessage, setActionMessage] = useState("请选择企业，并准备官方文档。");
  const [financialReport, setFinancialReport] = useState<FinancialReportPayload | null>(null);
  const [financialReportLoading, setFinancialReportLoading] = useState(false);
  const [financialReportError, setFinancialReportError] = useState<string | null>(null);

  const unifiedRisks = useMemo(
    () => buildUnifiedRiskItems(displayRisks, financialAnalysis, financialReport),
    [displayRisks, financialAnalysis, financialReport],
  );
  const riskSummary = useMemo(
    () => ({
      total: unifiedRisks.length,
      document: unifiedRisks.filter((item) => item.sourceKinds.includes("document")).length,
      announcement: unifiedRisks.filter((item) => item.sourceKinds.includes("announcement")).length,
      data: unifiedRisks.filter((item) => item.sourceKinds.includes("data")).length,
      financial: unifiedRisks.filter((item) => item.sourceKinds.includes("financial")).length,
      score: Math.max(0, ...unifiedRisks.map((item) => item.riskScore ?? 0)),
    }),
    [unifiedRisks],
  );
  const showResults = unifiedRisks.length > 0;

  const loadFinancialReport = useCallback(
    async (options?: { force?: boolean; signal?: AbortSignal }) => {
      if (!currentEnterpriseId) {
        setFinancialReport(null);
        setFinancialReportError(null);
        setFinancialReportLoading(false);
        return;
      }
      setFinancialReportLoading(true);
      setFinancialReportError(null);
      try {
        const payload = await api.getFinancialReport(currentEnterpriseId, {
          includeQuarterly: true,
          force: options?.force,
          signal: options?.signal,
        });
        setFinancialReport(payload);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setFinancialReport(null);
        setFinancialReportError(error instanceof Error ? error.message : "财报数据读取失败。");
      } finally {
        if (!options?.signal?.aborted) {
          setFinancialReportLoading(false);
        }
      }
    },
    [currentEnterpriseId],
  );

  useEffect(() => {
    setDisplayRisks([]);
    setFinancialReport(null);
    setFinancialReportError(null);
    setFinancialReportLoading(false);
  }, [currentEnterpriseId]);

  useEffect(() => {
    setDisplayRisks(risks ?? []);
  }, [risks]);

  useEffect(() => {
    const controller = new AbortController();
    void loadFinancialReport({ signal: controller.signal });
    return () => {
      controller.abort();
    };
  }, [loadFinancialReport]);

  useEffect(() => {
    if (!currentEnterpriseId) {
      setActionMessage("请先选择企业。");
      return;
    }
    if (running) {
      setActionMessage("正在执行风险分析，并刷新财报聚合。");
      return;
    }
    if (risksLoading || readinessLoading || dashboardLoading || financialAnalysisLoading || financialReportLoading) {
      setActionMessage("正在汇集风险分析。");
      return;
    }
    if (showResults) {
      return;
    }
    if (readiness?.manual_parse_required) {
      setActionMessage(`官方文档已同步，还有 ${readiness.documents_pending_parse} 份待解析。`);
      return;
    }
    if (readiness && !readiness.risk_analysis_ready) {
      setActionMessage(readiness.risk_analysis_message);
      return;
    }
    setActionMessage("暂无风险项。可先运行风险分析，或补充更多文档。");
  }, [
    currentEnterpriseId,
    dashboardLoading,
    financialAnalysisLoading,
    financialReportLoading,
    readiness,
    readinessLoading,
    risksLoading,
    running,
    showResults,
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
      await Promise.allSettled([
        refreshDashboard(),
        refreshRisks(),
        refreshReadiness(),
        refreshFinancialAnalysis(),
        loadFinancialReport({ force: true }),
      ]);
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : "风险分析运行失败。");
    } finally {
      setRunning(false);
    }
  };

  const pageTitle = useMemo(() => {
    if (!currentEnterprise) {
      return "风险分析";
    }
    return `${currentEnterprise.name} 风险分析`;
  }, [currentEnterprise]);

  return (
    <div className="space-y-6 pb-10">
      <section className="audit-overview-panel relative overflow-hidden rounded-[28px] border border-[#1d1912]/10 px-6 py-6 text-[#15130f] shadow-[0_20px_55px_rgba(21,19,15,0.08)]">
        <div className="relative z-10 grid gap-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
          <div>
            <p className="font-mono text-[0.68rem] font-semibold uppercase tracking-[0.24em] text-[#8f3148]">
              风险分析
            </p>
            <h2 className="mt-3 text-3xl font-black tracking-normal text-[#15130f]">{pageTitle}</h2>
            {!showResults ? (
              <p className="mt-3 max-w-3xl text-sm font-semibold leading-6 text-[#5d503b]">{actionMessage}</p>
            ) : null}
            {currentEnterpriseId ? (
              <p className="mt-3 text-xs font-semibold uppercase tracking-[0.16em] text-[#8a7759]">
                企业 ID：{currentEnterpriseId}
              </p>
            ) : null}
          </div>
          <Button
            onClick={() => void runAnalysis()}
            disabled={running || dashboard?.analysis_status === "running" || !currentEnterpriseId || !readiness?.risk_analysis_ready}
            className="min-h-11 bg-[#15130f] px-5 font-bold text-[#fffaf0] hover:bg-[#3f3628]"
          >
            {running || dashboard?.analysis_status === "running" ? "分析中..." : "运行风险分析"}
          </Button>
        </div>

        <div className="relative z-10 mt-5 grid gap-3 md:grid-cols-6">
          <SummaryChip label="风险总数" value={`${riskSummary.total} 项`} />
          <SummaryChip label="文档风险数量" value={`${riskSummary.document} 项`} />
          <SummaryChip label="公告风险数量" value={`${riskSummary.announcement} 项`} />
          <SummaryChip label="数据风险数量" value={`${riskSummary.data} 项`} />
          <SummaryChip label="财报风险数量" value={`${riskSummary.financial} 项`} />
          <SummaryChip label="总得分" value={riskSummary.score.toFixed(1)} />
        </div>
      </section>

      {enterpriseError ? (
        <RiskStateBox tone="error">{enterpriseError}</RiskStateBox>
      ) : !currentEnterpriseId ? (
        <RiskStateBox>当前没有可用企业。</RiskStateBox>
      ) : readinessError ? (
        <RiskStateBox tone="error">{readinessError}</RiskStateBox>
      ) : dashboardError && !showResults ? (
        <RiskStateBox tone="error">{dashboardError}</RiskStateBox>
      ) : risksError && !showResults ? (
        <RiskStateBox tone="error">{risksError}</RiskStateBox>
      ) : financialAnalysisError && !showResults ? (
        <RiskStateBox tone="error">{financialAnalysisError}</RiskStateBox>
      ) : financialReportError && !showResults ? (
        <RiskStateBox tone="error">{financialReportError}</RiskStateBox>
      ) : dashboardLoading || risksLoading || financialAnalysisLoading || financialReportLoading ? (
        <RiskStateBox>正在加载风险分析...</RiskStateBox>
      ) : showResults ? (
        <RiskTable
          risks={unifiedRisks}
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
        <RiskStateBox>当前企业暂无可展示风险项。完成文档解析后，这里会统一展示文档、公告、数据和财报风险。</RiskStateBox>
      )}
    </div>
  );
}

function SummaryChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-[#1d1912]/10 bg-[#fffdf7]/88 px-4 py-3">
      <p className="font-mono text-[0.65rem] font-bold uppercase tracking-[0.18em] text-[#8f3148]">{label}</p>
      <p className="mt-2 text-lg font-black text-[#15130f]">{value}</p>
    </div>
  );
}

