"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import type { FinancialReportPayload } from "@auditpilot/shared-types";
import { Printer } from "lucide-react";

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
  formatNumber,
  formatPercent,
  generateFinancialSummaries,
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
        <h2 className="text-lg font-semibold tracking-tight text-foreground">{title}</h2>
        {description ? <p className="text-sm leading-6 text-muted-foreground">{description}</p> : null}
      </div>
      {children}
    </section>
  );
}

function MetricCard({ metric }: { metric: MetricCard }) {
  return (
    <Card className="financial-print-block flex min-h-[138px] flex-col justify-between gap-5 p-5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium text-muted-foreground">{metric.label}</p>
        <span className="rounded-md border bg-muted px-2 py-1 font-mono text-[0.68rem] font-semibold text-muted-foreground">
          {metric.period}
        </span>
      </div>
      <div className="flex flex-col gap-2">
        <p className="font-mono text-2xl font-semibold tracking-tight text-foreground">{metric.value}</p>
        {metric.hint ? <p className="text-xs leading-5 text-muted-foreground">{metric.hint}</p> : null}
      </div>
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
      hint: "归属母公司股东",
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
    {
      label: "EPS",
      value: formatNumber(latest?.eps),
      period,
      hint: "基本每股收益",
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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!currentEnterpriseId) {
      setReport(null);
      setError(null);
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    setLoading(true);
    setError(null);

    api
      .getFinancialReport(currentEnterpriseId, { includeQuarterly: true, signal: controller.signal })
      .then((payload) => {
        setReport(payload);
      })
      .catch((fetchError) => {
        if (fetchError instanceof DOMException && fetchError.name === "AbortError") {
          return;
        }
        setReport(null);
        setError(fetchError instanceof Error ? fetchError.message : "财报数据读取失败。");
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });

    return () => {
      controller.abort();
    };
  }, [currentEnterpriseId]);

  const rows = report?.rows ?? [];
  const sortedRows = useMemo(() => sortFinancialRowsDesc(rows), [rows]);
  const ascendingRows = useMemo(() => sortFinancialRowsAsc(rows), [rows]);
  const latest = useMemo(() => getLatestFinancialRow(rows), [rows]);
  const metrics = useMemo(() => buildMetricCards(latest), [latest]);
  const summaries = useMemo(
    () => (report?.summaries?.length ? report.summaries.map((item) => item.text) : generateFinancialSummaries(rows)),
    [report?.summaries, rows],
  );
  const trendOption = useMemo(() => buildFinancialTrendOption(rows), [rows]);
  const firstPeriod = report?.period_range.start ?? ascendingRows[0]?.report_period ?? "--";
  const lastPeriod = report?.period_range.end ?? ascendingRows[ascendingRows.length - 1]?.report_period ?? "--";
  const updatedAt = formatDateTime(report?.updated_at);

  const handlePrint = () => {
    window.print();
  };

  const hasRows = sortedRows.length > 0;

  return (
    <div className="financial-print-page flex flex-col gap-6 pb-10">
      <Card className="financial-print-section">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Financial Reports</p>
              <h1 className="text-3xl font-semibold tracking-tight text-foreground">财报数据总览</h1>
            </div>
            <div className="grid gap-3 text-sm text-muted-foreground sm:grid-cols-2 xl:grid-cols-4">
              <div>
                <p className="text-xs uppercase tracking-[0.18em]">公司名称</p>
                <p className="mt-1 font-medium text-foreground">{report?.company_name ?? currentEnterprise?.name ?? "--"}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.18em]">股票代码</p>
                <p className="mt-1 font-mono font-medium text-foreground">{report?.ticker ?? currentEnterprise?.ticker ?? "--"}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.18em]">展示区间</p>
                <p className="mt-1 font-mono font-medium text-foreground">
                  {firstPeriod} - {lastPeriod}
                </p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.18em]">最后更新</p>
                <p className="mt-1 font-mono font-medium text-foreground">{updatedAt}</p>
              </div>
            </div>
            <p className="max-w-3xl text-sm leading-6 text-muted-foreground">
              数据来源：{report?.data_source ?? "等待接口返回"}。页面只展示后端接口数据。
            </p>
          </div>
          <Button onClick={handlePrint} data-print-hidden>
            <Printer className="mr-2 h-4 w-4" />
            导出 PDF
          </Button>
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
      ) : error ? (
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
          {report?.stale ? (
            <Alert variant="warning">
              <AlertTitle>数据未刷新</AlertTitle>
              <AlertDescription>{report.refresh_error ?? "当前展示已入库的 AkShare 数据。"}</AlertDescription>
            </Alert>
          ) : null}

          <FinancialSection title="核心指标摘要" description="展示最新一期财报。">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {metrics.map((metric) => (
                <MetricCard key={metric.label} metric={metric} />
              ))}
            </div>
          </FinancialSection>

          <FinancialSection title="季度趋势" description="按 report_period 展示。">
            <Card className="financial-print-block p-4">
              <EChart height={360} option={trendOption} />
            </Card>
          </FinancialSection>

          <FinancialSection title="自动摘要" description="基于接口返回数据。">
            <Card className="financial-print-block">
              <ul className="flex flex-col gap-3 text-sm leading-6 text-foreground">
                {summaries.map((summary) => (
                  <li key={summary} className="border-l-2 border-primary/50 pl-3">
                    {summary}
                  </li>
                ))}
              </ul>
            </Card>
          </FinancialSection>

          <FinancialSection title="财报明细表" description="按 report_period 倒序。">
            <Card className="financial-print-table p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>年份</TableHead>
                    <TableHead>季度</TableHead>
                    <TableHead>report_period</TableHead>
                    <TableHead className="text-right">营业收入</TableHead>
                    <TableHead className="text-right">收入同比</TableHead>
                    <TableHead className="text-right">收入环比</TableHead>
                    <TableHead className="text-right">归母净利</TableHead>
                    <TableHead className="text-right">扣非净利</TableHead>
                    <TableHead className="text-right">毛利率</TableHead>
                    <TableHead className="text-right">净利率</TableHead>
                    <TableHead className="text-right">资产负债率</TableHead>
                    <TableHead className="text-right">经营现金流</TableHead>
                    <TableHead className="text-right">ROE</TableHead>
                    <TableHead className="text-right">EPS</TableHead>
                    <TableHead>source</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sortedRows.map((row) => (
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
                      <TableCell className="text-right font-mono">{formatPercent(row.roe)}</TableCell>
                      <TableCell className="text-right font-mono">{formatNumber(row.eps)}</TableCell>
                      <TableCell className="whitespace-nowrap">{row.source}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          </FinancialSection>
        </>
      )}
    </div>
  );
}
