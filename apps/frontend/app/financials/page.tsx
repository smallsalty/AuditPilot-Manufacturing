"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import type { FinancialIndustryComparisonMetric, FinancialReportPayload } from "@auditpilot/shared-types";
import { Printer, RefreshCw } from "lucide-react";

import { EChart } from "@/components/echart";
import { useEnterpriseContext } from "@/components/enterprise-provider";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import {
  buildFinancialTrendOption,
  formatNumber,
  formatMoney,
  formatPercent,
  getLatestFinancialRow,
  sortFinancialRowsAsc,
  sortFinancialRowsDesc,
  type FinancialReportRow,
} from "@/lib/financials";

type MetricCard = {
  label: string;
  value: string;
  period: string;
  hint?: string;
};

type IndustryComparisonCardModel = {
  label: string;
  value: string;
  companyValue: string;
  industryValue: string;
  industryRange: string;
  gap: string;
  sampleText: string;
  referenceText: string;
  selectedIndustryText: string;
  confidenceText: string;
  periodText: string;
  available: boolean;
};

type ReportRequestState = "idle" | "loading" | "refreshing" | "success" | "error";
type IndustryRefreshState = "idle" | "refreshing" | "success" | "error";

function FinancialSection({
  title,
  description,
  action,
  children,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="financial-print-section flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-1">
          <h2 className="audit-title text-lg">{title}</h2>
          {description ? <p className="audit-copy text-sm">{description}</p> : null}
        </div>
        {action ? (
          <div className="flex shrink-0 items-center gap-2" data-print-hidden>
            {action}
          </div>
        ) : null}
      </div>
      {children}
    </section>
  );
}

function MetricCard({ metric }: { metric: MetricCard }) {
  return (
    <Card className="financial-print-block flex min-h-[138px] flex-col justify-between gap-5 p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-semibold text-[#5d503b]">{metric.label}</p>
        <span className="rounded-full border border-[#d8c8aa] bg-[#f8f3e8] px-2 py-1 font-mono text-[0.68rem] font-bold text-[#6c5d45]">
          {metric.period}
        </span>
      </div>
      <div className="flex flex-col gap-2">
        <p className="font-mono text-2xl font-black tracking-normal text-[#15130f]">{metric.value}</p>
        {metric.hint ? <p className="text-xs font-semibold leading-5 text-[#5d503b]">{metric.hint}</p> : null}
      </div>
    </Card>
  );
}

function IndustryComparisonCard({ metric }: { metric: IndustryComparisonCardModel }) {
  return (
    <Card className="financial-print-block flex min-h-[138px] flex-col justify-between gap-5 p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-semibold text-[#5d503b]">{metric.label}</p>
        <span className="rounded-full border border-[#d8c8aa] bg-[#f8f3e8] px-2 py-1 font-mono text-[0.68rem] font-bold text-[#6c5d45]">
          {metric.available ? metric.periodText : "行业数据未加载"}
        </span>
      </div>
      {metric.available ? (
        <div className="flex flex-col gap-3">
          <div className="grid gap-2 text-xs font-semibold leading-5 text-[#5d503b] sm:grid-cols-3">
            <span>中位 {metric.industryValue}</span>
            <span>{metric.industryRange}</span>
            <span>{metric.gap}</span>
          </div>
          <p className="text-xs font-semibold leading-5 text-[#8a7759]">{metric.sampleText}</p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <p className="font-mono text-2xl font-black tracking-normal text-[#15130f]">{metric.value}</p>
          <p className="text-xs font-semibold leading-5 text-[#5d503b]">{metric.selectedIndustryText}</p>
          <p className="text-xs font-semibold leading-5 text-[#8a7759]">公司值 {metric.companyValue}</p>
        </div>
      )}
    </Card>
  );
}

function filterRecentYears(rows: FinancialReportRow[]): FinancialReportRow[] {
  if (!rows.length) {
    return [];
  }
  const latestYear = Math.max(...rows.map((row) => row.year));
  return rows.filter((row) => row.year >= latestYear - 2);
}

function FinancialReportTable({ rows }: { rows: FinancialReportRow[] }) {
  return (
    <Card className="financial-print-table p-0">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>年份</TableHead>
            <TableHead>季度</TableHead>
            <TableHead>报告期</TableHead>
            <TableHead className="text-right">营业收入</TableHead>
            <TableHead className="text-right">收入增长</TableHead>
            <TableHead className="text-right">收入同比</TableHead>
            <TableHead className="text-right">收入环比</TableHead>
            <TableHead className="text-right">归母净利</TableHead>
            <TableHead className="text-right">扣非净利</TableHead>
            <TableHead className="text-right">毛利率</TableHead>
            <TableHead className="text-right">净利率</TableHead>
            <TableHead className="text-right">应收周转</TableHead>
            <TableHead className="text-right">存货周转</TableHead>
            <TableHead className="text-right">资产负债率</TableHead>
            <TableHead className="text-right">费用率</TableHead>
            <TableHead className="text-right">经营现金流</TableHead>
            <TableHead className="text-right">固定资产</TableHead>
            <TableHead className="text-right">ROE</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.report_period}>
              <TableCell>{row.year}</TableCell>
              <TableCell>{row.quarter}</TableCell>
              <TableCell className="font-mono font-medium">{row.report_period}</TableCell>
              <TableCell className="text-right font-mono">{formatMoney(row.revenue)}</TableCell>
              <TableCell className="text-right font-mono">{formatPercent(row.revenue_growth)}</TableCell>
              <TableCell className="text-right font-mono">{formatPercent(row.revenue_yoy)}</TableCell>
              <TableCell className="text-right font-mono">{formatPercent(row.revenue_qoq)}</TableCell>
              <TableCell className="text-right font-mono">{formatMoney(row.net_profit)}</TableCell>
              <TableCell className="text-right font-mono">{formatMoney(row.deduct_net_profit)}</TableCell>
              <TableCell className="text-right font-mono">{formatPercent(row.gross_margin)}</TableCell>
              <TableCell className="text-right font-mono">{formatPercent(row.net_margin)}</TableCell>
              <TableCell className="text-right font-mono">{formatNumber(row.ar_turnover)}</TableCell>
              <TableCell className="text-right font-mono">{formatNumber(row.inventory_turnover)}</TableCell>
              <TableCell className="text-right font-mono">{formatPercent(row.debt_ratio)}</TableCell>
              <TableCell className="text-right font-mono">{formatPercent(row.expense_ratio)}</TableCell>
              <TableCell className="text-right font-mono">{formatMoney(row.ocf)}</TableCell>
              <TableCell className="text-right font-mono">{formatMoney(row.fixed_assets)}</TableCell>
              <TableCell className="text-right font-mono">{formatPercent(row.roe)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}

function buildMetricCards(latest: FinancialReportRow | null): MetricCard[] {
  const period = latest?.report_period ?? "--";
  return [
    {
      label: "营业收入",
      value: formatMoney(latest?.revenue),
      period,
      hint: `同比 ${formatPercent(latest?.revenue_yoy)} / 环比 ${formatPercent(latest?.revenue_qoq)}`,
    },
    {
      label: "营业收入增长率",
      value: formatPercent(latest?.revenue_growth),
      period,
      hint: "本期收入 / 上年同期",
    },
    {
      label: "归母净利",
      value: formatMoney(latest?.net_profit),
      period,
      hint: "归属公司股东",
    },
    {
      label: "扣非净利",
      value: formatMoney(latest?.deduct_net_profit),
      period,
      hint: "扣除非经常损益",
    },
    {
      label: "毛利率",
      value: formatPercent(latest?.gross_margin),
      period,
      hint: "收入口径",
    },
    {
      label: "净利率",
      value: formatPercent(latest?.net_margin),
      period,
      hint: "净利 / 收入",
    },
    {
      label: "应收账款周转率",
      value: formatNumber(latest?.ar_turnover),
      period,
      hint: "收入 / 平均应收账款",
    },
    {
      label: "存货周转率",
      value: formatNumber(latest?.inventory_turnover),
      period,
      hint: "成本 / 平均存货",
    },
    {
      label: "经营现金流",
      value: formatMoney(latest?.ocf),
      period,
      hint: "现金流量表",
    },
    {
      label: "固定资产",
      value: formatMoney(latest?.fixed_assets),
      period,
      hint: "期末余额",
    },
    {
      label: "资产负债率",
      value: formatPercent(latest?.debt_ratio),
      period,
      hint: "总负债 / 总资产",
    },
    {
      label: "费用率",
      value: formatPercent(latest?.expense_ratio),
      period,
      hint: "销售、管理、研发、财务",
    },
    {
      label: "ROE",
      value: formatPercent(latest?.roe),
      period,
      hint: "净资产收益率",
    },
  ];
}

function buildIndustryComparisonCards(report: FinancialReportPayload | null): IndustryComparisonCardModel[] {
  const comparison = report?.industry_comparison;
  const referenceName = resolveReferenceIndustryName(report);
  return [
    buildIndustryComparisonCard("营业收入增长率", comparison?.revenue_growth, "percent", false, referenceName),
    buildIndustryComparisonCard("毛利率", comparison?.gross_margin, "percent", false, referenceName),
    buildIndustryComparisonCard("净利率", comparison?.net_margin, "percent", false, referenceName),
    buildIndustryComparisonCard("营业收入", comparison?.revenue, "money", true, referenceName),
    buildIndustryComparisonCard("应收账款周转率", comparison?.ar_turnover, "number", true, referenceName),
    buildIndustryComparisonCard("存货周转率", comparison?.inventory_turnover, "number", true, referenceName),
    buildIndustryComparisonCard("资产负债率", comparison?.debt_ratio, "percent", false, referenceName),
    buildIndustryComparisonCard("费用率", comparison?.expense_ratio, "percent", false, referenceName),
  ];
}

function buildIndustryComparisonCard(
  label: string,
  metric: FinancialIndustryComparisonMetric | null | undefined,
  valueType: "percent" | "number" | "money",
  usePercentGap: boolean,
  referenceName: string,
): IndustryComparisonCardModel {
  const available = Boolean(metric?.available);
  const companyValue = formatIndustryValue(metric?.company_value, valueType);
  const industryValue = formatIndustryValue(metric?.industry_median ?? metric?.industry_mean, valueType);
  const metricReferenceName = metric?.industry_name ?? referenceName;
  return {
    label,
    value: available ? industryValue : "行业数据未加载",
    companyValue: companyValue === "--" ? "待补" : companyValue,
    industryValue,
    industryRange: `区间 ${formatIndustryValue(metric?.p25, valueType)} - ${formatIndustryValue(metric?.p75, valueType)}`,
    gap: `差异 ${formatSignedGap(metric?.gap, metric?.gap_pct, valueType, usePercentGap)}`,
    sampleText: `样本 ${metric?.sample_count ?? 0}`,
    referenceText: `参考${metricReferenceName}行业同行`,
    selectedIndustryText: `已选择：${formatIndustryName(metricReferenceName)}`,
    confidenceText: formatConfidence(metric?.confidence),
    periodText: formatPeriodText(metric),
    available,
  };
}

function resolveReferenceIndustryName(report: FinancialReportPayload | null): string {
  const comparison = report?.industry_comparison;
  return comparison?.reference_industry_name ?? comparison?.industry_name ?? "未识别行业";
}

function getIndustryComparisonMetrics(
  report: FinancialReportPayload | null,
): Array<FinancialIndustryComparisonMetric | null | undefined> {
  const comparison = report?.industry_comparison;
  return comparison
    ? [
        comparison.revenue_growth,
        comparison.gross_margin,
        comparison.net_margin,
        comparison.revenue,
        comparison.ar_turnover,
        comparison.inventory_turnover,
        comparison.debt_ratio,
        comparison.expense_ratio,
      ]
    : [];
}

function hasAvailableIndustryMetrics(report: FinancialReportPayload | null): boolean {
  return getIndustryComparisonMetrics(report).some((metric) => metric?.available);
}

function buildIndustryStatusText(report: FinancialReportPayload | null): string {
  const referenceName = resolveReferenceIndustryName(report);
  const hasIndustryData = hasAvailableIndustryMetrics(report);
  return hasIndustryData
    ? `参考${formatIndustryName(referenceName)}同行`
    : `已选择${formatIndustryName(referenceName)}，行业数据未加载`;
}

function sanitizeIndustryRefreshError(error: unknown): string {
  const message = error instanceof Error ? error.message : "";
  if (/HTTPSConnectionPool|ProxyError|Max retries|RemoteDisconnected|eastmoney/i.test(message)) {
    return "行业基准刷新暂时不可用，请稍后再试。";
  }
  return message || "同行基准刷新失败。";
}

function formatIndustryName(value: string | null | undefined): string {
  const text = String(value || "未识别行业").trim() || "未识别行业";
  return text.endsWith("行业") || text.endsWith("业") ? text : `${text}行业`;
}

function formatIndustryValue(value: number | null | undefined, valueType: "percent" | "number" | "money"): string {
  if (valueType === "money") {
    return formatMoney(value);
  }
  return valueType === "percent" ? formatPercent(value) : formatNumber(value);
}

function formatSignedPoint(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "--";
  }
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}个百分点`;
}

function formatSignedPercentFromRatio(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "--";
  }
  const percent = value * 100;
  return `${percent >= 0 ? "+" : ""}${percent.toFixed(2)}%`;
}

function formatSignedGap(
  gap: number | null | undefined,
  gapPct: number | null | undefined,
  valueType: "percent" | "number" | "money",
  usePercentGap: boolean,
): string {
  if (usePercentGap) {
    return formatSignedPercentFromRatio(gapPct);
  }
  if (valueType === "money") {
    return formatMoney(gap);
  }
  if (valueType === "number") {
    if (typeof gap !== "number" || !Number.isFinite(gap)) {
      return "--";
    }
    return `${gap >= 0 ? "+" : ""}${gap.toFixed(2)}`;
  }
  return formatSignedPoint(gap);
}

function formatConfidence(confidence: string | null | undefined): string {
  const labels: Record<string, string> = {
    high: "高可信",
    limited: "可参考",
    cautious: "谨慎看",
  };
  return labels[String(confidence || "")] ?? "缓存中";
}

function formatPeriodText(metric: FinancialIndustryComparisonMetric | null | undefined): string {
  if (!metric?.period) {
    return "期间待补";
  }
  if (metric.period_aligned) {
    return metric.period;
  }
  const range = metric.actual_peer_period_range?.length ? metric.actual_peer_period_range.join("~") : metric.period;
  return `${range}弱参考`;
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN");
}

export default function FinancialsPage() {
  const { currentEnterprise, currentEnterpriseId, enterpriseError } = useEnterpriseContext();
  const [report, setReport] = useState<FinancialReportPayload | null>(null);
  const [requestState, setRequestState] = useState<ReportRequestState>("idle");
  const [industryRefreshState, setIndustryRefreshState] = useState<IndustryRefreshState>("idle");
  const [industryRefreshError, setIndustryRefreshError] = useState<string | null>(null);
  const [industryRefreshNotice, setIndustryRefreshNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchReport = useCallback(
    (force: boolean, signal?: AbortSignal) => {
      if (!currentEnterpriseId) {
        return;
      }

      setRequestState(force ? "refreshing" : "loading");
      setError(null);
      setIndustryRefreshError(null);
      setIndustryRefreshNotice(null);

      api
        .getFinancialReport(currentEnterpriseId, { force, includeQuarterly: true, signal })
        .then((payload) => {
          setReport(payload);
          setRequestState(force ? "success" : "idle");
        })
        .catch((fetchError) => {
          if (fetchError instanceof DOMException && fetchError.name === "AbortError") {
            return;
          }
          if (!force) {
            setReport(null);
          }
          setError(fetchError instanceof Error ? fetchError.message : "财报数据读取失败。");
          setRequestState("error");
        });
    },
    [currentEnterpriseId],
  );

  useEffect(() => {
    if (!currentEnterpriseId) {
      setReport(null);
      setError(null);
      setIndustryRefreshError(null);
      setIndustryRefreshNotice(null);
      setIndustryRefreshState("idle");
      setRequestState("idle");
      return;
    }

    const controller = new AbortController();
    fetchReport(false, controller.signal);

    return () => {
      controller.abort();
    };
  }, [currentEnterpriseId, fetchReport]);

  const rows = report?.rows ?? [];
  const annualRows = useMemo(
    () => filterRecentYears(sortFinancialRowsDesc(rows.filter((row) => row.quarter === "FY"))),
    [rows],
  );
  const quarterlyRows = useMemo(
    () => filterRecentYears(sortFinancialRowsDesc(rows.filter((row) => row.quarter !== "FY"))),
    [rows],
  );
  const displayedRows = useMemo(() => sortFinancialRowsDesc([...annualRows, ...quarterlyRows]), [annualRows, quarterlyRows]);
  const ascendingRows = useMemo(() => sortFinancialRowsAsc(displayedRows), [displayedRows]);
  const latest = useMemo(() => getLatestFinancialRow(displayedRows), [displayedRows]);
  const metrics = useMemo(() => buildMetricCards(latest), [latest]);
  const industryCards = useMemo(() => buildIndustryComparisonCards(report), [report]);
  const industryStatusText = useMemo(() => buildIndustryStatusText(report), [report]);
  const dataRisks = report?.data_risks ?? [];
  const trendOption = useMemo(() => buildFinancialTrendOption(quarterlyRows), [quarterlyRows]);
  const firstPeriod = ascendingRows[0]?.report_period ?? "--";
  const lastPeriod = ascendingRows[ascendingRows.length - 1]?.report_period ?? "--";
  const updatedAt = formatDateTime(report?.updated_at);

  const handlePrint = () => {
    window.print();
  };

  const handleRefresh = () => {
    fetchReport(true);
  };

  const handleIndustryRefresh = () => {
    if (!currentEnterpriseId) {
      return;
    }
    setIndustryRefreshState("refreshing");
    setIndustryRefreshError(null);
    setIndustryRefreshNotice(null);
    api
      .refreshIndustryBenchmarks(currentEnterpriseId)
      .then((payload) => {
        setReport(payload);
        if (hasAvailableIndustryMetrics(payload)) {
          setIndustryRefreshState("success");
          setIndustryRefreshNotice(null);
          return;
        }
        setIndustryRefreshState("idle");
        setIndustryRefreshNotice("本次没有获取到行业数据，已保留当前页面。");
      })
      .catch((refreshError) => {
        setIndustryRefreshNotice(null);
        setIndustryRefreshError(sanitizeIndustryRefreshError(refreshError));
        setIndustryRefreshState("error");
      });
  };

  const hasRows = displayedRows.length > 0;
  const loading = requestState === "loading";
  const refreshing = requestState === "refreshing";
  const industryRefreshing = industryRefreshState === "refreshing";
  const statusText =
    requestState === "loading"
      ? "正在读取 AkShare"
      : requestState === "refreshing"
        ? "正在刷新 AkShare"
        : requestState === "success"
          ? "刷新完成"
          : requestState === "error" && report
            ? "刷新失败，保留旧数据"
            : "空闲";

  return (
    <div className="financial-print-page flex flex-col gap-6 pb-10">
      <Card className="financial-print-section">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <p className="audit-label">Financial Reports</p>
              <h1 className="audit-title text-3xl">财报数据总览</h1>
            </div>
            <div className="grid gap-3 text-sm font-semibold text-[#5d503b] sm:grid-cols-2 xl:grid-cols-4">
              <div>
                <p className="text-xs uppercase tracking-[0.18em]">公司名称</p>
                <p className="mt-1 font-black text-[#15130f]">{report?.company_name ?? currentEnterprise?.name ?? "--"}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.18em]">股票代码</p>
                <p className="mt-1 font-mono font-black text-[#15130f]">{report?.ticker ?? currentEnterprise?.ticker ?? "--"}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.18em]">展示区间</p>
                <p className="mt-1 font-mono font-black text-[#15130f]">
                  {firstPeriod} - {lastPeriod}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.18em]">最后更新</p>
                <p className="mt-1 font-mono font-black text-[#15130f]">{updatedAt}</p>
              </div>
            </div>
            <p className="audit-copy text-sm">
              运行状态：{statusText}。
            </p>
          </div>
          <div className="flex flex-wrap gap-2" data-print-hidden>
            <Button onClick={handleRefresh} disabled={!currentEnterpriseId || refreshing}>
              <RefreshCw className={`mr-2 h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
              {refreshing ? "刷新中" : "刷新 AkShare"}
            </Button>
            <Button onClick={handlePrint}>
              <Printer className="mr-2 h-4 w-4" />
              导出 PDF
            </Button>
          </div>
        </div>
      </Card>

      {enterpriseError ? (
        <Alert variant="destructive">
          <AlertTitle>企业不可用</AlertTitle>
          <AlertDescription>{enterpriseError}</AlertDescription>
        </Alert>
      ) : !currentEnterpriseId ? (
        <Alert>
          <AlertTitle>请先选企业</AlertTitle>
          <AlertDescription>当前没有企业上下文。</AlertDescription>
        </Alert>
      ) : loading ? (
        <Alert>
          <AlertTitle>正在读取</AlertTitle>
          <AlertDescription>正在读取 AkShare 财报数据。</AlertDescription>
        </Alert>
      ) : error && !report ? (
        <Alert variant="destructive">
          <AlertTitle>财报读取失败</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : !hasRows ? (
        <Alert>
          <AlertTitle>暂无财报数据</AlertTitle>
          <AlertDescription>后端接口没有返回可展示的财报行。</AlertDescription>
        </Alert>
      ) : (
        <>
          {refreshing ? (
            <Alert>
              <AlertTitle>正在刷新</AlertTitle>
              <AlertDescription>正在重新拉取 AkShare 财报数据。</AlertDescription>
            </Alert>
          ) : null}

          {error && report ? (
            <Alert variant="warning">
              <AlertTitle>刷新失败</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {report?.stale ? (
            <Alert variant="warning">
              <AlertTitle>数据未刷新</AlertTitle>
              <AlertDescription>{report.refresh_error ?? "当前展示已入库的 AkShare 数据。"}</AlertDescription>
            </Alert>
          ) : null}

          <FinancialSection title="核心指标摘要">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {metrics.map((metric) => (
                <MetricCard key={metric.label} metric={metric} />
              ))}
            </div>
          </FinancialSection>

          <FinancialSection
            title="行业对比"
            description={industryStatusText}
            action={
              <Button onClick={handleIndustryRefresh} disabled={!currentEnterpriseId || industryRefreshing}>
                <RefreshCw className={`mr-2 h-4 w-4 ${industryRefreshing ? "animate-spin" : ""}`} />
                {industryRefreshing ? "刷新中" : "刷新同行基准"}
              </Button>
            }
          >
            {industryRefreshError ? (
              <Alert variant="warning">
                <AlertTitle>同行基准刷新失败</AlertTitle>
                <AlertDescription>{industryRefreshError}</AlertDescription>
              </Alert>
            ) : null}
            {industryRefreshNotice ? (
              <Alert>
                <AlertTitle>行业数据未更新</AlertTitle>
                <AlertDescription>{industryRefreshNotice}</AlertDescription>
              </Alert>
            ) : null}
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {industryCards.map((metric) => (
                <IndustryComparisonCard key={metric.label} metric={metric} />
              ))}
            </div>
          </FinancialSection>

          <FinancialSection title="季度趋势">
            <Card className="financial-print-block p-4">
              <EChart height={360} option={trendOption} />
            </Card>
          </FinancialSection>

          <FinancialSection title="数据风险">
            <Card className="financial-print-block">
              <ul className="flex flex-col gap-3 text-sm leading-6 text-foreground">
                {dataRisks.length ? (
                  dataRisks.map((risk) => (
                    <li key={risk.rule_code} className="border-l-4 border-[#e24c74] pl-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold">{risk.risk_name}</span>
                        <span className="font-mono text-xs font-semibold text-[#8a7759]">
                          {risk.risk_level} / {risk.risk_score.toFixed(2)}
                        </span>
                      </div>
                      <p className="text-[#5d503b]">{risk.judgment}</p>
                      <p>{risk.evidence}</p>
                    </li>
                  ))
                ) : (
                  <li className="border-l-4 border-[#e24c74] pl-3">近4个季度未触发数据风险规则。</li>
                )}
              </ul>
            </Card>
          </FinancialSection>

          <FinancialSection title="财年对比">
            <FinancialReportTable rows={annualRows} />
          </FinancialSection>

          <FinancialSection title="季度对比">
            <FinancialReportTable rows={quarterlyRows} />
          </FinancialSection>
        </>
      )}
    </div>
  );
}
