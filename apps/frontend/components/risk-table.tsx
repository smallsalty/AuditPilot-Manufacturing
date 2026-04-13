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
    <Card className="overflow-hidden p-0">
      <div className="grid grid-cols-[2fr_0.7fr_0.7fr_0.7fr_0.8fr] gap-4 border-b border-white/10 px-6 py-4 text-xs uppercase tracking-[0.2em] text-steel">
        <span>风险项</span>
        <span>等级</span>
        <span>得分</span>
        <span>证据数</span>
        <span>来源</span>
      </div>
      <div className="divide-y divide-white/10">
        {risks.map((risk) => (
          <details key={risk.id} className="group">
            <summary className="grid cursor-pointer list-none grid-cols-[2fr_0.7fr_0.7fr_0.7fr_0.8fr] gap-4 px-6 py-5">
              <div>
                <p className="font-medium text-white">{risk.risk_name}</p>
                <p className="mt-2 text-sm text-haze/70">{risk.llm_summary ?? risk.reasons.join("；")}</p>
              </div>
              <div className="flex items-start">
                <Badge value={risk.risk_level} />
              </div>
              <div className="text-xl font-semibold text-white">{risk.risk_score.toFixed(1)}</div>
              <div className="text-lg font-semibold text-amber-300">{risk.evidence_chain.length}</div>
              <div className="flex items-start">
                <Badge value={risk.source_type} />
              </div>
            </summary>
            <div className="space-y-5 border-t border-white/10 bg-black/10 px-6 py-5 text-sm text-haze/85">
              <div>
                <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">命中原因</p>
                <div className="flex flex-wrap gap-2">
                  {risk.reasons.map((reason) => (
                    <span key={reason} className="rounded-full bg-white/5 px-3 py-1">
                      {reason}
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">证据索引</p>
                {risk.evidence_chain.length > 0 ? (
                  <div className="space-y-2">
                    {risk.evidence_chain.map((evidence) => (
                      <div key={`${risk.id}-${evidence.evidence_id}`} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded-full bg-amber-400/15 px-3 py-1 text-xs font-medium text-amber-200">
                            {evidence.evidence_id}
                          </span>
                          <span className="text-xs uppercase tracking-[0.2em] text-steel">
                            {EVIDENCE_TYPE_LABELS[evidence.evidence_type] ?? evidence.evidence_type}
                          </span>
                          {evidence.source_label ? (
                            <span className="text-xs uppercase tracking-[0.2em] text-steel">{evidence.source_label}</span>
                          ) : null}
                          {evidence.published_at ? (
                            <span className="text-xs uppercase tracking-[0.2em] text-steel">{evidence.published_at}</span>
                          ) : null}
                        </div>
                        <p className="mt-3 font-medium text-white">{evidence.title}</p>
                        <p className="mt-1 text-haze/75">{evidence.snippet}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
                    暂无直接证据
                  </div>
                )}
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <div>
                  <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">重点科目 / 流程</p>
                  <p>{risk.focus_accounts.join("、") || "暂无"}</p>
                  <p className="mt-2 text-haze/70">{risk.focus_processes.join("、") || "暂无"}</p>
                </div>
                <div>
                  <p className="mb-2 text-xs uppercase tracking-[0.2em] text-steel">建议程序</p>
                  <p>{risk.recommended_procedures.join("、") || "暂无"}</p>
                </div>
              </div>
            </div>
          </details>
        ))}
      </div>
    </Card>
  );
}
