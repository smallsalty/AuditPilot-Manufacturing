import type { FinancialReportRowPayload } from "@auditpilot/shared-types";

export type FinancialReportRow = FinancialReportRowPayload;

const quarterWeight: Record<string, number> = {
  Q1: 1,
  Q2: 2,
  Q3: 3,
  Q4: 4,
  FY: 5,
};

function isFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function periodRank(row: FinancialReportRow): number {
  const quarter = String(row.quarter || "").toUpperCase();
  const parsedQuarter = Number(quarter.replace("Q", ""));
  const rank = quarterWeight[quarter] ?? (Number.isFinite(parsedQuarter) ? parsedQuarter : 0);
  return row.year * 10 + rank;
}

export function sortFinancialRowsDesc(rows: FinancialReportRow[]): FinancialReportRow[] {
  return [...rows].sort((a, b) => periodRank(b) - periodRank(a));
}

export function sortFinancialRowsAsc(rows: FinancialReportRow[]): FinancialReportRow[] {
  return [...rows].sort((a, b) => periodRank(a) - periodRank(b));
}

export function getLatestFinancialRow(rows: FinancialReportRow[]): FinancialReportRow | null {
  return sortFinancialRowsDesc(rows)[0] ?? null;
}

export function formatMoney(value: number | null | undefined): string {
  if (!isFiniteNumber(value)) {
    return "--";
  }
  const absValue = Math.abs(value);
  if (absValue >= 100000000) {
    return `${(value / 100000000).toFixed(2)} 亿元`;
  }
  if (absValue >= 10000) {
    return `${(value / 10000).toFixed(2)} 万元`;
  }
  return `${value.toLocaleString("zh-CN")} 元`;
}

export function formatPercent(value: number | null | undefined): string {
  return isFiniteNumber(value) ? `${value.toFixed(2)}%` : "--";
}

export function formatNumber(value: number | null | undefined): string {
  return isFiniteNumber(value) ? value.toFixed(2) : "--";
}

function formatChange(value: number | null | undefined): string {
  if (!isFiniteNumber(value)) {
    return "--";
  }
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function describeDirection(current: number | null | undefined, previous: number | null | undefined, metric: string): string | null {
  if (!isFiniteNumber(current) || !isFiniteNumber(previous)) {
    return null;
  }
  if (current === previous) {
    return `${metric}较上期持平。`;
  }
  return `${metric}较上期${current > previous ? "上升" : "下降"}${Math.abs(current - previous).toFixed(2)}个百分点。`;
}

export function generateFinancialSummaries(rows: FinancialReportRow[]): string[] {
  const sortedRows = sortFinancialRowsDesc(rows);
  const latest = sortedRows[0];
  const previous = sortedRows[1];
  if (!latest) {
    return ["暂无结构化财报数据。"];
  }

  const summaries: string[] = [];
  summaries.push(`${latest.report_period}收入为${formatMoney(latest.revenue)}，同比${formatChange(latest.revenue_yoy)}。`);

  if (previous && isFiniteNumber(latest.net_profit) && isFiniteNumber(previous.net_profit)) {
    const profitDirection = latest.net_profit >= previous.net_profit ? "改善" : "下滑";
    summaries.push(`归母净利较${previous.report_period}${profitDirection}，变动${formatMoney(latest.net_profit - previous.net_profit)}。`);
  }

  if (isFiniteNumber(latest.ocf) && isFiniteNumber(latest.net_profit)) {
    const sameDirection = latest.ocf >= 0 && latest.net_profit >= 0;
    summaries.push(`经营现金流为${formatMoney(latest.ocf)}，与利润方向${sameDirection ? "一致" : "不一致"}。`);
  }

  const marginSummary = previous ? describeDirection(latest.gross_margin, previous.gross_margin, "毛利率") : null;
  if (marginSummary) {
    summaries.push(marginSummary);
  }

  const debtSummary = previous ? describeDirection(latest.debt_ratio, previous.debt_ratio, "资产负债率") : null;
  if (debtSummary) {
    summaries.push(debtSummary);
  }

  return summaries.slice(0, 5);
}

export function buildFinancialTrendOption(rows: FinancialReportRow[]): object {
  const chartRows = sortFinancialRowsAsc(rows);
  return {
    animation: false,
    color: ["#15130f", "#8f3148", "#5d503b"],
    grid: {
      top: 42,
      right: 28,
      bottom: 44,
      left: 18,
      containLabel: true,
    },
    legend: {
      top: 0,
      right: 8,
      textStyle: {
        color: "#5d503b",
        fontSize: 12,
      },
    },
    tooltip: {
      trigger: "axis",
      valueFormatter: (value: number) => formatMoney(value),
      backgroundColor: "rgba(255, 253, 247, 0.98)",
      borderColor: "rgba(93, 80, 59, 0.18)",
      textStyle: {
        color: "#15130f",
      },
    },
    xAxis: {
      type: "category",
      data: chartRows.map((item) => item.report_period),
      boundaryGap: false,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "rgba(93, 80, 59, 0.35)" } },
      axisLabel: {
        color: "#5d503b",
        fontSize: 12,
        margin: 14,
      },
    },
    yAxis: {
      type: "value",
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: {
        color: "#5d503b",
        fontSize: 12,
        formatter: (value: number) => `${(value / 100000000).toFixed(0)}亿`,
      },
      splitLine: { lineStyle: { color: "rgba(93, 80, 59, 0.14)" } },
    },
    series: [
      {
        name: "营业收入",
        type: "line",
        symbol: "circle",
        symbolSize: 7,
        data: chartRows.map((item) => item.revenue),
        lineStyle: { width: 2.6, type: "solid" },
      },
      {
        name: "归母净利",
        type: "line",
        symbol: "rect",
        symbolSize: 7,
        data: chartRows.map((item) => item.net_profit),
        lineStyle: { width: 2.6, type: "dashed" },
      },
      {
        name: "经营现金流",
        type: "line",
        symbol: "triangle",
        symbolSize: 8,
        data: chartRows.map((item) => item.ocf),
        lineStyle: { width: 2.6, type: "dotted" },
      },
    ],
  };
}
