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
  const radarLineColor = "rgba(93, 80, 59, 0.22)";
  const radarFillColor = "rgba(255, 253, 247, 0.54)";
  const radarTextColor = "#5d503b";
  const radarAreaColor = "rgba(226, 76, 116, 0.16)";
  const radarStrokeColor = "#8f3148";
  return {
    animationDuration: 700,
    animationEasing: "cubicOut",
    radar: {
      radius: "67%",
      center: ["50%", "56%"],
      splitNumber: 4,
      axisName: {
        color: radarTextColor,
        fontSize: 12,
        fontWeight: 600,
      },
      axisLine: { lineStyle: { color: radarLineColor, width: 1 } },
      splitArea: {
        areaStyle: {
          color: ["rgba(255, 253, 247, 0.24)", radarFillColor],
        },
      },
      splitLine: { lineStyle: { color: radarLineColor, width: 1.1 } },
      indicator: radarData.map((item) => ({ name: item.name, max: 100 })),
    },
    series: [
      {
        type: "radar",
        data: [
          {
            value: radarData.map((item) => item.value),
            areaStyle: { color: radarAreaColor },
            lineStyle: { color: radarStrokeColor, width: 2.5 },
            itemStyle: { color: radarStrokeColor },
            symbol: "circle",
            symbolSize: 8,
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
    animationDuration: 700,
    animationEasing: "cubicOut",
    grid: {
      top: 36,
      right: 18,
      bottom: 26,
      left: 12,
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: trendData.map((item) => item.report_period),
      boundaryGap: false,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "rgba(93, 80, 59, 0.22)" } },
      axisLabel: {
        color: "#7a6a4f",
        fontSize: 12,
        margin: 14,
      },
    },
    yAxis: {
      type: "value",
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: {
        color: "#7a6a4f",
        fontSize: 12,
      },
      splitLine: { lineStyle: { color: "rgba(93, 80, 59, 0.12)" } },
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(255, 253, 247, 0.96)",
      borderColor: "rgba(93, 80, 59, 0.16)",
      textStyle: {
        color: "#15130f",
      },
    },
    series: [
      {
        data: trendData.map((item) => item.risk_score),
        type: "line",
        smooth: true,
        symbol: "circle",
        symbolSize: 8,
        itemStyle: {
          color: "#15130f",
          borderColor: "#fffdf7",
          borderWidth: 2,
        },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: "rgba(226, 76, 116, 0.22)" },
              { offset: 1, color: "rgba(216, 200, 170, 0.12)" },
            ],
          },
        },
        lineStyle: { color: "#c94b35", width: 3 },
      },
    ],
  };
}
