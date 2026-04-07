"use client";

import dynamic from "next/dynamic";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

export function EChart({ option, height = 320 }: { option: object; height?: number }) {
  return <ReactECharts option={option} style={{ height }} notMerge lazyUpdate />;
}

