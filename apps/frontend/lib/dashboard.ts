import type { DashboardPayload } from "@auditpilot/shared-types";

type RadarPoint = DashboardPayload["radar"][number];
type TrendPoint = DashboardPayload["trend"][number];
type TopRiskCard = DashboardPayload["top_risks"][number];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function isValidRadarPoint(value: unknown): value is RadarPoint {
  if (!isRecord(value)) return false;
  return isNonEmptyString(value.name) && isFiniteNumber(value.value);
}

export function isValidTrendPoint(value: unknown): value is TrendPoint {
  if (!isRecord(value)) return false;
  return isNonEmptyString(value.report_period) && isFiniteNumber(value.risk_score);
}

export function isValidTopRiskCard(value: unknown): value is TopRiskCard {
  if (!isRecord(value)) return false;
  return (
    isFiniteNumber(value.id) &&
    isNonEmptyString(value.risk_name) &&
    isNonEmptyString(value.risk_level) &&
    isFiniteNumber(value.risk_score) &&
    isNonEmptyString(value.source_type)
  );
}

export function getSafeRadarData(dashboard: unknown): RadarPoint[] {
  if (!isRecord(dashboard) || !Array.isArray(dashboard.radar)) {
    return [];
  }
  return dashboard.radar.filter(isValidRadarPoint);
}

export function getSafeTrendData(dashboard: unknown): TrendPoint[] {
  if (!isRecord(dashboard) || !Array.isArray(dashboard.trend)) {
    return [];
  }
  return dashboard.trend.filter(isValidTrendPoint);
}

export function getSafeTopRisks(dashboard: unknown): TopRiskCard[] {
  if (!isRecord(dashboard) || !Array.isArray(dashboard.top_risks)) {
    return [];
  }
  return dashboard.top_risks.filter(isValidTopRiskCard);
}

export function hasValidRadarData(dashboard: unknown): boolean {
  return getSafeRadarData(dashboard).length >= 3;
}

export function hasValidTrendData(dashboard: unknown): boolean {
  return getSafeTrendData(dashboard).length >= 1;
}

export function buildRadarOption(radarInput: unknown): object | null {
  const radarData = Array.isArray(radarInput) ? radarInput.filter(isValidRadarPoint) : [];
  if (radarData.length < 3) {
    return null;
  }
  return {
    radar: {
      radius: "65%",
      splitNumber: 4,
      axisName: { color: "#cbd5e1" },
      splitArea: { areaStyle: { color: ["rgba(255,255,255,0.02)"] } },
      splitLine: { lineStyle: { color: "rgba(255,255,255,0.08)" } },
      indicator: radarData.map((item) => ({ name: item.name, max: 100 })),
    },
    series: [
      {
        type: "radar",
        data: [
          {
            value: radarData.map((item) => item.value),
            areaStyle: { color: "rgba(217,119,6,0.28)" },
            lineStyle: { color: "#f59e0b" },
            itemStyle: { color: "#f59e0b" },
          },
        ],
      },
    ],
  };
}

export function buildTrendOption(trendInput: unknown): object | null {
  const trendData = Array.isArray(trendInput) ? trendInput.filter(isValidTrendPoint) : [];
  if (trendData.length < 1) {
    return null;
  }
  return {
    xAxis: {
      type: "category",
      data: trendData.map((item) => item.report_period),
      axisLabel: { color: "#cbd5e1" },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: "#cbd5e1" },
      splitLine: { lineStyle: { color: "rgba(255,255,255,0.08)" } },
    },
    tooltip: { trigger: "axis" },
    series: [
      {
        data: trendData.map((item) => item.risk_score),
        type: "line",
        smooth: true,
        areaStyle: { color: "rgba(16,185,129,0.18)" },
        lineStyle: { color: "#10b981", width: 3 },
      },
    ],
  };
}
