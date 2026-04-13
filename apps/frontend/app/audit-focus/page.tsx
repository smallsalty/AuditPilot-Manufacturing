"use client";

import { useMemo } from "react";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { Card } from "@/components/ui/card";
import { useAuditFocusResource, useReadinessResource } from "@/lib/enterprise-resources";

function ChipGroup({ title, items, emptyText }: { title: string; items: string[]; emptyText: string }) {
  return (
    <Card>
      <p className="text-xs uppercase tracking-[0.24em] text-steel">{title}</p>
      {items.length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-3">
          {items.map((item) => (
            <span key={item} className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-haze/85">
              {item}
            </span>
          ))}
        </div>
      ) : (
        <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">{emptyText}</div>
      )}
    </Card>
  );
}

export default function AuditFocusPage() {
  const { currentEnterprise, currentEnterpriseId, enterpriseError } = useEnterpriseContext();
  const { data: readiness, loading: readinessLoading, error: readinessError } = useReadinessResource(currentEnterpriseId);
  const { data: focus, loading: focusLoading, error: focusError } = useAuditFocusResource(currentEnterpriseId);

  const pageState = useMemo(() => {
    if (enterpriseError) {
      return { kind: "error", message: `企业列表加载失败：${enterpriseError}` };
    }
    if (!currentEnterpriseId || !currentEnterprise) {
      return { kind: "empty", message: "请先选择企业。" };
    }
    if (readinessLoading || focusLoading) {
      return { kind: "loading", message: "正在加载审计重点..." };
    }
    if (readinessError) {
      return { kind: "error", message: `状态加载失败：${readinessError}` };
    }
    if (focusError) {
      return { kind: "error", message: `审计重点加载失败：${focusError}` };
    }
    if (readiness?.risk_analysis_status === "running") {
      return { kind: "waiting", message: "风险分析正在执行中，完成后将自动生成审计重点。" };
    }
    if (readiness?.risk_analysis_status === "failed") {
      return { kind: "error", message: focus?.last_error ?? "最近一次风险分析失败，请先重新运行分析。" };
    }
    if (readiness?.risk_analysis_status !== "completed") {
      return { kind: "empty", message: "当前企业尚未完成风险分析，请先运行风险分析。" };
    }
    return { kind: "ready", message: "以下建议基于当前企业的规则命中、财务异常和官方公告证据生成。" };
  }, [
    currentEnterprise,
    currentEnterpriseId,
    enterpriseError,
    focus?.last_error,
    focusError,
    focusLoading,
    readiness,
    readinessError,
    readinessLoading,
  ]);

  return (
    <div className="space-y-6 pb-10">
      <Card>
        <p className="text-xs uppercase tracking-[0.24em] text-steel">审计重点</p>
        <h2 className="mt-3 text-3xl font-semibold text-white">
          {currentEnterprise ? `${currentEnterprise.name} 审计重点提示` : "审计重点提示"}
        </h2>
        <p className="mt-2 text-haze/75">{pageState.message}</p>
      </Card>

      {pageState.kind === "loading" || pageState.kind === "empty" || pageState.kind === "waiting" ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-haze/75">{pageState.message}</div>
        </Card>
      ) : pageState.kind === "error" ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-5 text-sm text-red-100">{pageState.message}</div>
        </Card>
      ) : (
        <>
          <section className="grid gap-5 lg:grid-cols-3">
            <ChipGroup title="重点科目" items={focus?.focus_accounts ?? []} emptyText="暂无重点科目。" />
            <ChipGroup title="重点流程" items={focus?.focus_processes ?? []} emptyText="暂无重点流程。" />
            <ChipGroup title="建议程序" items={focus?.recommended_procedures ?? []} emptyText="暂无建议程序。" />
          </section>

          <section className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
            <Card>
              <p className="text-xs uppercase tracking-[0.24em] text-steel">建议证据</p>
              {focus?.evidence_types?.length ? (
                <div className="mt-4 flex flex-wrap gap-3">
                  {focus.evidence_types.map((item) => (
                    <span key={item} className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-haze/85">
                      {item}
                    </span>
                  ))}
                </div>
              ) : (
                <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">暂无建议证据。</div>
              )}
            </Card>

            <Card>
              <p className="text-xs uppercase tracking-[0.24em] text-steel">重点建议摘要</p>
              {focus?.recommendation_items?.length ? (
                <div className="mt-4 space-y-3">
                  {focus.recommendation_items.map((item, index) => (
                    <div key={`${item.text}-${index}`} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                      <p className="text-sm text-white">{item.text}</p>
                      {item.sources.length ? (
                        <div className="mt-3 flex flex-wrap gap-2">
                          {item.sources.map((source) => (
                            <span key={source} className="rounded-full bg-black/15 px-3 py-1 text-xs text-haze/75">
                              {source}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
                  当前企业暂无可展示的审计重点建议。
                </div>
              )}
            </Card>
          </section>
        </>
      )}
    </div>
  );
}
