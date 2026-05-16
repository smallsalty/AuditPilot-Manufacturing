"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import type { FinancialReportPayload } from "@auditpilot/shared-types";
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

type ReportRequestState = "idle" | "loading" | "refreshing" | "success" | "error";

function FinancialSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="financial-print-section flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2 className="audit-title text-lg">{title}</h2>
        {description ? <p className="audit-copy text-sm">{description}</p> : null}
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
            <TableHead className="text-right">收入同比</TableHead>
            <TableHead className="text-right">收入环比</TableHead>
            <TableHead className="text-right">归母净利</TableHead>
            <TableHead className="text-right">扣非净利</TableHead>
            <TableHead className="text-right">毛利率</TableHead>
            <TableHead className="text-right">净利率</TableHead>
            <TableHead className="text-right">资产负债率</TableHead>
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
              <TableCell className="text-right font-mono">{formatPercent(row.revenue_yoy)}</TableCell>
              <TableCell className="text-right font-mono">{formatPercent(row.revenue_qoq)}</TableCell>
              <TableCell className="text-right font-mono">{formatMoney(row.net_profit)}</TableCell>
              <TableCell className="text-right font-mono">{formatMoney(row.deduct_net_profit)}</TableCell>
              <TableCell className="text-right font-mono">{formatPercent(row.gross_margin)}</TableCell>
              <TableCell className="text-right font-mono">{formatPercent(row.net_margin)}</TableCell>
              <TableCell className="text-right font-mono">{formatPercent(row.debt_ratio)}</TableCell>
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
      label: "ROE",
      value: formatPercent(latest?.roe),
      period,
      hint: "净资产收益率",
    },
  ];
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
  const [error, setError] = useState<string | null>(null);

  const fetchReport = useCallback(
    (force: boolean, signal?: AbortSignal) => {
      if (!currentEnterpriseId) {
        return;
      }

      setRequestState(force ? "refreshing" : "loading");
      setError(null);

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

  const hasRows = displayedRows.length > 0;
  const loading = requestState === "loading";
  const refreshing = requestState === "refreshing";
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
