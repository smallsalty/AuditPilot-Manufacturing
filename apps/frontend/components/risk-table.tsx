"use client";

import { useState } from "react";
import type { RiskResultPayload } from "@auditpilot/shared-types";

import {
  CANONICAL_RISK_KEYS,
  formatCanonicalRiskKey,
  formatRuleCode,
  isUnmappedLabel,
} from "@/lib/display-labels";
import type { UnifiedRiskEvidence, UnifiedRiskItem } from "@/lib/risk-display";
import { api } from "@/lib/api";

export function RiskTable({
  risks,
  enterpriseId,
  onChanged,
}: {
  risks: UnifiedRiskItem[];
  enterpriseId: number | null;
  onChanged?: () => Promise<void> | void;
}) {
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [mergeValues, setMergeValues] = useState<Record<string, string>>({});

  const ignoreRisk = async (risk: RiskResultPayload) => {
    if (!enterpriseId || !risk.canonical_risk_key) return;
    setBusyKey(risk.canonical_risk_key);
    try {
      await api.overrideRiskResult(enterpriseId, risk.canonical_risk_key, { ignored: true });
      await onChanged?.();
    } finally {
      setBusyKey(null);
    }
  };

  const mergeRisk = async (risk: RiskResultPayload) => {
    if (!enterpriseId || !risk.canonical_risk_key) return;
    const mergeToKey = mergeValues[risk.canonical_risk_key];
    if (!mergeToKey || mergeToKey === risk.canonical_risk_key) return;
    setBusyKey(risk.canonical_risk_key);
    try {
      await api.overrideRiskResult(enterpriseId, risk.canonical_risk_key, { merge_to_key: mergeToKey });
      await onChanged?.();
    } finally {
      setBusyKey(null);
    }
  };

  return (
    <div className="space-y-4">
      {risks.map((risk, index) => {
        const operationRisk = risk.operationRisk;
        const operationKey = operationRisk?.canonical_risk_key;
        return (
          <article
            key={risk.id}
            className="audit-overview-panel relative overflow-hidden rounded-[28px] border border-[#1d1912]/10 px-5 py-5 text-[#15130f] shadow-[0_20px_55px_rgba(21,19,15,0.08)]"
          >
            <details className="group">
              <summary className="list-none cursor-pointer">
                <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_13rem] lg:items-start">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#15130f] font-mono text-xs font-black text-[#fffaf0]">
                        {index + 1}
                      </span>
                      <p className="font-mono text-[0.68rem] font-bold uppercase tracking-[0.22em] text-[#8f3148]">
                        风险类型
                      </p>
                      <h3 className="min-w-0 text-xl font-black leading-7 tracking-normal text-[#15130f]">
                        {risk.riskType}
                      </h3>
                    </div>
                    <p className="mt-3 max-w-4xl text-sm font-semibold leading-6 text-[#5d503b]">{risk.summary}</p>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <span className="rounded-full border border-[#1d1912]/10 bg-[#fffdf7]/90 px-3 py-1 text-xs font-bold text-[#5d503b]">
                        来源：{formatSourceLabels(risk.sourceLabels)}
                      </span>
                    </div>
                  </div>
                  <div className={scoreBoxClassName(risk)}>
                    <p className="font-mono text-[0.68rem] font-bold uppercase tracking-[0.2em]">得分</p>
                    <p className="mt-2 font-mono text-4xl font-black leading-none">{formatScore(risk)}</p>
                    <p className="mt-2 text-xs font-bold">{scoreHint(risk)}</p>
                  </div>
                </div>
              </summary>

              <div className="mt-5 space-y-5 border-t border-[#1d1912]/10 pt-5 text-sm">
                <section className="grid gap-4 lg:grid-cols-[0.85fr_1.15fr]">
                  <div className="rounded-2xl border border-[#1d1912]/10 bg-[#fffdf7]/88 p-4">
                    <p className="font-mono text-[0.68rem] font-bold uppercase tracking-[0.22em] text-[#8f3148]">
                      风险类型 + 具体风险语句
                    </p>
                    <p className="mt-3 text-base font-black leading-7 text-[#15130f]">{risk.riskType}</p>
                    <p className="mt-2 text-sm font-semibold leading-6 text-[#5d503b]">{risk.riskStatement}</p>
                    {risk.sourceRules.length ? (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {risk.sourceRules.map((rule) => (
                          <span
                            key={rule}
                            className="rounded-full border border-[#d8c8aa] bg-[#f8f3e8] px-3 py-1 text-xs font-bold text-[#6c5d45]"
                          >
                            {formatRuleLabel(rule)}
                          </span>
                        ))}
                      </div>
                    ) : null}
                    {risk.relatedRiskType ? (
                      <div className="mt-3 rounded-xl border border-[#d8c8aa] bg-[#f8f3e8] px-3 py-2 text-xs font-bold text-[#6c5d45]">
                        关联风险类型：{risk.relatedRiskType}
                      </div>
                    ) : null}
                  </div>

                  <div className="rounded-2xl border border-[#1d1912]/10 bg-[#fffdf7]/88 p-4">
                    <p className="font-mono text-[0.68rem] font-bold uppercase tracking-[0.22em] text-[#8f3148]">
                      来源文件
                    </p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {risk.sourceFiles.map((file) => (
                        <span
                          key={file}
                          className="rounded-full border border-[#1d1912]/10 bg-[#f8f3e8] px-3 py-1 text-xs font-bold text-[#3f3628]"
                        >
                          {file}
                        </span>
                      ))}
                    </div>
                  </div>
                </section>

                <EvidenceSection title="证据原文" items={risk.rawEvidence} emptyText="暂无可展示的证据原文。" />

                {operationRisk && operationKey ? (
                  <section className="rounded-2xl border border-[#1d1912]/10 bg-[#fffdf7]/88 p-4">
                    <p className="font-mono text-[0.68rem] font-bold uppercase tracking-[0.22em] text-[#8f3148]">
                      操作
                    </p>
                    <div className="mt-3 flex flex-col gap-3 lg:flex-row lg:items-center">
                      <button
                        type="button"
                        className="cursor-pointer rounded-xl border border-[#1d1912]/15 bg-[#15130f] px-4 py-3 text-sm font-bold text-[#fffaf0] transition-colors duration-200 hover:bg-[#3f3628] disabled:cursor-not-allowed disabled:opacity-50"
                        disabled={busyKey === operationKey}
                        onClick={(event) => {
                          event.preventDefault();
                          void ignoreRisk(operationRisk);
                        }}
                      >
                        {busyKey === operationKey ? "处理中..." : "忽略该风险"}
                      </button>
                      <select
                        className="min-h-11 rounded-xl border border-[#1d1912]/15 bg-[#fffdf7] px-3 py-3 text-sm font-semibold text-[#15130f]"
                        value={mergeValues[operationKey] ?? ""}
                        onChange={(event) =>
                          setMergeValues((current) => ({ ...current, [operationKey]: event.target.value }))
                        }
                      >
                        <option value="">合并到标准风险键</option>
                        {CANONICAL_RISK_KEYS.filter((key) => key !== operationKey).map((key) => (
                          <option key={key} value={key}>
                            {formatCanonicalRiskKey(key)}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        className="cursor-pointer rounded-xl border border-[#1d1912]/15 bg-[#fffdf7] px-4 py-3 text-sm font-bold text-[#15130f] transition-colors duration-200 hover:bg-[#f8f3e8] disabled:cursor-not-allowed disabled:opacity-50"
                        disabled={busyKey === operationKey || !mergeValues[operationKey]}
                        onClick={(event) => {
                          event.preventDefault();
                          void mergeRisk(operationRisk);
                        }}
                      >
                        合并风险
                      </button>
                    </div>
                  </section>
                ) : null}
              </div>
            </details>
          </article>
        );
      })}
    </div>
  );
}

function EvidenceSection({
  title,
  items,
  emptyText,
}: {
  title: string;
  items: UnifiedRiskEvidence[];
  emptyText: string;
}) {
  return (
    <section className="rounded-2xl border border-[#1d1912]/10 bg-[#fffdf7]/88 p-4">
      <p className="font-mono text-[0.68rem] font-bold uppercase tracking-[0.22em] text-[#8f3148]">{title}</p>
      {items.length ? (
        <div className="mt-3 space-y-3">
          {items.map((item, index) => (
            <div key={`${item.id}-${index}`} className="rounded-xl border border-[#1d1912]/10 bg-[#f8f3e8] p-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-[#1d1912]/10 bg-[#15130f] px-2.5 py-1 font-mono text-[0.68rem] font-black text-[#fffaf0]">
                  {index + 1}
                </span>
                <p className="font-black text-[#15130f]">{item.sourceFile}</p>
              </div>
              <p className="mt-3 text-sm font-bold text-[#3f3628]">{item.title}</p>
              <p className="mt-2 whitespace-pre-wrap text-sm font-medium leading-6 text-[#5d503b]">{item.rawText}</p>
              {item.meta.length ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {item.meta.map((meta) => (
                    <span
                      key={meta}
                      className="rounded-full border border-[#d8c8aa] bg-[#fffdf7] px-2.5 py-1 text-xs font-semibold text-[#6c5d45]"
                    >
                      {meta}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-3 rounded-xl border border-dashed border-[#d8c8aa] bg-[#f8f3e8]/70 p-4 text-sm font-semibold text-[#6c5d45]">
          {emptyText}
        </div>
      )}
    </section>
  );
}

function formatScore(risk: UnifiedRiskItem): string {
  return typeof risk.riskScore === "number" ? risk.riskScore.toFixed(1) : "--";
}

function formatRuleLabel(rule: string): string {
  const label = formatRuleCode(rule);
  return isUnmappedLabel(label) ? "其他规则" : label;
}

function formatSourceLabels(labels: string[]): string {
  const uniqueLabels = labels.filter((label, index, array) => Boolean(label) && array.indexOf(label) === index);
  return uniqueLabels.length ? uniqueLabels.join("、") : "暂无";
}

function scoreHint(risk: UnifiedRiskItem): string {
  if (risk.riskLevel === "SPECIAL" || typeof risk.riskScore !== "number") {
    return "专项分析";
  }
  if (risk.riskLevel?.toUpperCase() === "HIGH" || (typeof risk.riskScore === "number" && risk.riskScore >= 80)) {
    return "高风险";
  }
  if (risk.riskLevel?.toUpperCase() === "LOW" || (typeof risk.riskScore === "number" && risk.riskScore < 60)) {
    return "低风险";
  }
  return "中风险";
}

function scoreBoxClassName(risk: UnifiedRiskItem): string {
  const base = "rounded-2xl border px-4 py-4 text-right";
  if (risk.riskLevel?.toUpperCase() === "HIGH" || (typeof risk.riskScore === "number" && risk.riskScore >= 80)) {
    return `${base} border-[#c94b35]/25 bg-[#c94b35]/10 text-[#8c2e22]`;
  }
  if (risk.riskLevel?.toUpperCase() === "LOW" || (typeof risk.riskScore === "number" && risk.riskScore < 60)) {
    return `${base} border-[#047857]/20 bg-[#047857]/10 text-[#065f46]`;
  }
  return `${base} border-[#b7791f]/25 bg-[#b7791f]/10 text-[#8a4f12]`;
}
