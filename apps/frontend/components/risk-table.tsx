"use client";

import { useState } from "react";
import type { RiskResultPayload } from "@auditpilot/shared-types";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import {
  CANONICAL_RISK_KEYS,
  formatCanonicalRiskKey,
  formatEvidenceStatus,
  formatEvidenceType,
  formatEventType,
  formatRiskLevel,
  formatRuleCode,
  formatSeverity,
  formatSourceMode,
  formatSourceType,
} from "@/lib/display-labels";

export function RiskTable({
  risks,
  enterpriseId,
  onChanged,
}: {
  risks: RiskResultPayload[];
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
      {risks.map((risk, index) => (
        <Card key={risk.id}>
          <details className="group">
            <summary className="list-none cursor-pointer">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-semibold text-amber-300">{index + 1}.</span>
                    <h3 className="text-lg font-semibold text-white">{risk.risk_name}</h3>
                    <Badge value={risk.risk_level} label={formatRiskLevel(risk.risk_level)} />
                  </div>
                  <p className="mt-3 text-sm text-haze/80">{risk.summary ?? risk.llm_summary ?? risk.reasons.join("；")}</p>
                  <div className="mt-3 flex flex-wrap gap-2 text-xs text-haze/65">
                    <span>
                      {risk.evidence_status
                        ? formatEvidenceStatus(risk.evidence_status)
                        : risk.source_mode
                          ? formatSourceMode(risk.source_mode)
                          : formatSourceType(risk.source_type)}
                    </span>
                    {risk.canonical_risk_key ? <span>{formatCanonicalRiskKey(risk.canonical_risk_key)}</span> : null}
                    <span>得分：{risk.risk_score.toFixed(1)}</span>
                    <span>证据：{risk.evidence_chain.length}</span>
                  </div>
                </div>
              </div>
            </summary>
            <div className="mt-5 space-y-5 border-t border-white/10 pt-5 text-sm text-haze/85">
              {risk.source_rules?.length ? (
                <section>
                  <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">规则补充</p>
                  <ol className="space-y-2">
                    {risk.source_rules.map((rule, ruleIndex) => (
                      <li key={rule} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                        {ruleIndex + 1}. {formatRuleCode(rule)}
                      </li>
                    ))}
                  </ol>
                </section>
              ) : null}

              {risk.source_events?.length ? (
                <section>
                  <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">事件来源</p>
                  <ol className="space-y-2">
                    {risk.source_events.map((event, eventIndex) => (
                      <li key={`${risk.id}-${eventIndex}`} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                        {eventIndex + 1}.{" "}
                        {[formatEventType(event.event_type), event.subject, event.event_date, formatSeverity(event.severity)]
                          .filter(Boolean)
                          .join(" | ")}
                      </li>
                    ))}
                  </ol>
                </section>
              ) : null}

              <section>
                <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">证据索引</p>
                {risk.evidence_chain.length > 0 ? (
                  <div className="space-y-3">
                    {risk.evidence_chain.map((evidence, evidenceIndex) => (
                      <div key={`${risk.id}-${evidence.evidence_id}`} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                        <p className="font-medium text-white">
                          {evidenceIndex + 1}. {evidence.title}
                        </p>
                        <p className="mt-2 text-haze/75">{evidence.snippet}</p>
                        <div className="mt-3 flex flex-wrap gap-2 text-xs text-haze/60">
                          <span>{formatEvidenceType(evidence.evidence_type)}</span>
                          {evidence.source_label ? <span>{evidence.source_label}</span> : null}
                          {evidence.published_at ? <span>{evidence.published_at}</span> : null}
                          {"section_title" in evidence && (evidence as Record<string, unknown>).section_title ? (
                            <span>{String((evidence as Record<string, unknown>).section_title)}</span>
                          ) : null}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">暂无直接证据。</div>
                )}
              </section>

              {risk.source_documents?.length ? (
                <section>
                  <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">来源文档</p>
                  <ol className="space-y-2">
                    {risk.source_documents.map((document, documentIndex) => (
                      <li key={`${document.document_id}-${document.document_name}`} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                        {documentIndex + 1}. {document.document_name}
                      </li>
                    ))}
                  </ol>
                </section>
              ) : null}

              {risk.recommended_procedures.length ? (
                <section>
                  <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">建议动作</p>
                  <ol className="space-y-2">
                    {risk.recommended_procedures.map((procedure, procedureIndex) => (
                      <li key={procedure} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                        {procedureIndex + 1}. {procedure}
                      </li>
                    ))}
                  </ol>
                </section>
              ) : null}

              {enterpriseId && risk.canonical_risk_key ? (
                <section>
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
                    <button
                      type="button"
                      className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-haze/80 disabled:opacity-50"
                      disabled={busyKey === risk.canonical_risk_key}
                      onClick={(event) => {
                        event.preventDefault();
                        void ignoreRisk(risk);
                      }}
                    >
                      {busyKey === risk.canonical_risk_key ? "处理中..." : "忽略该风险"}
                    </button>
                    <select
                      className="rounded-2xl border border-white/10 bg-white/5 px-3 py-3 text-sm text-haze/80"
                      value={mergeValues[risk.canonical_risk_key] ?? ""}
                      onChange={(event) =>
                        setMergeValues((current) => ({ ...current, [risk.canonical_risk_key as string]: event.target.value }))
                      }
                    >
                      <option value="">合并到标准风险键</option>
                      {CANONICAL_RISK_KEYS.filter((key) => key !== risk.canonical_risk_key).map((key) => (
                        <option key={key} value={key}>
                          {formatCanonicalRiskKey(key)}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-haze/80 disabled:opacity-50"
                      disabled={busyKey === risk.canonical_risk_key || !mergeValues[risk.canonical_risk_key]}
                      onClick={(event) => {
                        event.preventDefault();
                        void mergeRisk(risk);
                      }}
                    >
                      合并风险
                    </button>
                  </div>
                </section>
              ) : null}
            </div>
          </details>
        </Card>
      ))}
    </div>
  );
}
