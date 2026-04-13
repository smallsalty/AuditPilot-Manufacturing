import type { RiskResultPayload } from "@auditpilot/shared-types";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";

const EVIDENCE_TYPE_LABELS: Record<string, string> = {
  announcement: "公告",
  annual_report: "年报",
  penalty: "处罚",
  inquiry_letter: "问询",
  financial_indicator: "财务指标",
  industry_signal: "行业信号",
  uploaded_document: "上传文档",
  derived_risk_result: "派生结果",
};

export function RiskTable({ risks }: { risks: RiskResultPayload[] }) {
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
                    <Badge value={risk.risk_level} />
                  </div>
                  <p className="mt-3 text-sm text-haze/80">{risk.summary ?? risk.llm_summary ?? risk.reasons.join("；")}</p>
                  <div className="mt-3 flex flex-wrap gap-2 text-xs text-haze/65">
                    <span>来源模式：{risk.source_mode ?? risk.source_type}</span>
                    <span>得分：{risk.risk_score.toFixed(1)}</span>
                    <span>证据：{risk.evidence_chain.length}</span>
                  </div>
                </div>
              </div>
            </summary>
            <div className="mt-5 space-y-5 border-t border-white/10 pt-5 text-sm text-haze/85">
              {risk.source_rules?.length ? (
                <section>
                  <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">遵循规则</p>
                  <ol className="space-y-2">
                    {risk.source_rules.map((rule, ruleIndex) => (
                      <li key={rule} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                        {ruleIndex + 1}. {rule}
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
                          <span>{EVIDENCE_TYPE_LABELS[evidence.evidence_type] ?? evidence.evidence_type}</span>
                          {evidence.source_label ? <span>{evidence.source_label}</span> : null}
                          {evidence.published_at ? <span>{evidence.published_at}</span> : null}
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
            </div>
          </details>
        </Card>
      ))}
    </div>
  );
}
