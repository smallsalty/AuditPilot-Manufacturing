"use client";

import { useEffect, useState } from "react";
import type { RiskResultPayload } from "@auditpilot/shared-types";

import { RiskTable } from "@/components/risk-table";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";

export default function RisksPage() {
  const [enterpriseId] = useState(1);
  const [risks, setRisks] = useState<RiskResultPayload[]>([]);
  const [running, setRunning] = useState(false);
  const [message, setMessage] = useState("尚未运行分析");

  const loadResults = () => {
    api.getRiskResults(enterpriseId).then(setRisks).catch(() => setRisks([]));
  };

  useEffect(() => {
    loadResults();
  }, []);

  const runAnalysis = async () => {
    setRunning(true);
    setMessage("正在导入财务、风险事件和宏观数据...");
    try {
      await api.ingestFinancial(enterpriseId);
      await api.ingestRiskEvents(enterpriseId);
      await api.ingestMacro();
      const result = await api.runRiskAnalysis(enterpriseId);
      setRisks(result.results);
      setMessage(result.run.summary);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "运行失败");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-6 pb-10">
      <Card>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-steel">Risk Register</p>
            <h2 className="mt-3 text-3xl font-semibold text-white">风险清单与证据链</h2>
            <p className="mt-2 text-haze/75">{message}</p>
          </div>
          <Button onClick={runAnalysis} disabled={running}>
            {running ? "分析中..." : "运行风险分析"}
          </Button>
        </div>
      </Card>
      <RiskTable risks={risks} />
    </div>
  );
}

