"use client";

import { useMemo } from "react";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { Card } from "@/components/ui/card";
import { useAuditFocusResource, useReadinessResource } from "@/lib/enterprise-resources";

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
    if ((focus?.items?.length ?? 0) === 0 && !readiness?.qa_ready) {
      return { kind: "empty", message: "当前企业尚无可展示审计重点，请先解析文档或运行风险分析。" };
    }
    return { kind: "ready", message: "以下重点优先基于文档证据、规则命中和风险结果生成。" };
  }, [currentEnterprise, currentEnterpriseId, enterpriseError, focus?.items?.length, focusError, focusLoading, readiness?.qa_ready, readinessError, readinessLoading]);

  return (
    <div className="space-y-6 pb-10">
      <Card>
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">审计重点</p>
        <h2 className="mt-3 text-3xl font-semibold text-foreground">
          {currentEnterprise ? `${currentEnterprise.name} 审计重点提示` : "审计重点提示"}
        </h2>
        <p className="mt-2 text-muted-foreground">{pageState.message}</p>
      </Card>

      {pageState.kind === "loading" || pageState.kind === "empty" ? (
        <Card>
          <div className="rounded-xl border border-dashed bg-muted/30 p-5 text-sm text-muted-foreground">{pageState.message}</div>
        </Card>
      ) : pageState.kind === "error" ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-5 text-sm text-red-100">{pageState.message}</div>
        </Card>
      ) : (
        <div className="space-y-4">
          {(focus?.items ?? []).map((item, index) => (
            <Card key={item.id}>
              <details className="group">
                <summary className="list-none cursor-pointer">
                  <div className="flex items-start gap-3">
                    <span className="pt-0.5 text-sm font-semibold text-primary">{index + 1}.</span>
                    <div className="min-w-0 flex-1">
                      <h3 className="text-lg font-semibold text-foreground">{item.title}</h3>
                      <p className="mt-2 text-sm text-muted-foreground">{item.summary}</p>
                    </div>
                  </div>
                </summary>
                <div className="mt-4 space-y-4 border-t border-border pt-4">
                  {item.sources.length ? (
                    <section>
                      <p className="mb-2 text-xs uppercase tracking-[0.2em] text-muted-foreground">来源</p>
                      <div className="flex flex-wrap gap-2">
                        {item.sources.map((source) => (
                          <span key={source} className="rounded-full border border-border bg-muted/30 px-3 py-1 text-xs text-muted-foreground">
                            {source}
                          </span>
                        ))}
                      </div>
                    </section>
                  ) : null}

                  {item.evidence_preview?.length ? (
                    <section>
                      <p className="mb-2 text-xs uppercase tracking-[0.2em] text-muted-foreground">依据预览</p>
                      <ol className="space-y-2">
                        {item.evidence_preview.map((evidence) => (
                          <li key={evidence} className="rounded-xl border border-border bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
                            {evidence}
                          </li>
                        ))}
                      </ol>
                    </section>
                  ) : null}

                  {item.expanded_sections?.map((section) => (
                    <section key={section.title}>
                      <p className="mb-2 text-xs uppercase tracking-[0.2em] text-muted-foreground">{section.title}</p>
                      <ol className="space-y-2">
                        {section.items.map((detail) => (
                          <li key={detail} className="rounded-xl border border-border bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
                            {detail}
                          </li>
                        ))}
                      </ol>
                    </section>
                  ))}
                </div>
              </details>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
