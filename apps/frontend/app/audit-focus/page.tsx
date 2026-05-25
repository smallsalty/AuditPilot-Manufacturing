"use client";

import { useCallback, useMemo, useState, type ReactNode } from "react";
import type { AuditFocusPayload, RiskResultPayload } from "@auditpilot/shared-types";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { Button } from "@/components/ui/button";
import {
  useAuditFocusResource,
  useReadinessResource,
  useRiskResultsResource,
} from "@/lib/enterprise-resources";
import { formatCanonicalRiskKey, isUnmappedLabel } from "@/lib/display-labels";
import { compactText } from "@/lib/risk-display";

type FocusItem = NonNullable<AuditFocusPayload["items"]>[number];

export default function AuditFocusPage() {
  const { currentEnterprise, currentEnterpriseId, enterpriseError } = useEnterpriseContext();
  const { data: readiness, loading: readinessLoading, error: readinessError } = useReadinessResource(currentEnterpriseId);
  const { data: focus, loading: focusLoading, error: focusError, refresh: refreshFocus } = useAuditFocusResource(currentEnterpriseId);
  const { data: risks, loading: risksLoading } = useRiskResultsResource(currentEnterpriseId);
  const [refreshingAdvice, setRefreshingAdvice] = useState(false);

  const items = focus?.items ?? [];
  const riskByTitle = useMemo(() => buildRiskLookup(risks ?? []), [risks]);
  const pageSummary = useMemo(() => buildAdviceSummary(items, riskByTitle), [items, riskByTitle]);
  const handleRefreshAdvice = useCallback(async () => {
    if (!currentEnterpriseId || refreshingAdvice) {
      return;
    }
    setRefreshingAdvice(true);
    try {
      await refreshFocus({ force: true });
    } finally {
      setRefreshingAdvice(false);
    }
  }, [currentEnterpriseId, refreshFocus, refreshingAdvice]);

  const pageState = useMemo(() => {
    if (enterpriseError) {
      return { kind: "error", message: `企业列表加载失败：${enterpriseError}` };
    }
    if (!currentEnterpriseId || !currentEnterprise) {
      return { kind: "empty", message: "请先选择企业。" };
    }
    if (readinessLoading || focusLoading || risksLoading) {
      return { kind: "loading", message: "正在加载审计建议..." };
    }
    if (readinessError) {
      return { kind: "error", message: `状态加载失败：${readinessError}` };
    }
    if (focusError) {
      return { kind: "error", message: `审计建议加载失败：${focusError}` };
    }
    if ((focus?.items?.length ?? 0) === 0 && !readiness?.qa_ready) {
      return { kind: "empty", message: "当前企业尚无审计建议。先解析文档，或运行风险分析。" };
    }
    return { kind: "ready", message: "" };
  }, [
    currentEnterprise,
    currentEnterpriseId,
    enterpriseError,
    focus?.items?.length,
    focusError,
    focusLoading,
    readiness?.qa_ready,
    readinessError,
    readinessLoading,
    risksLoading,
  ]);

  return (
    <div className="space-y-6 pb-10">
      <section className="audit-overview-panel relative overflow-hidden rounded-[28px] border border-[#1d1912]/10 px-6 py-6 text-[#15130f] shadow-[0_20px_55px_rgba(21,19,15,0.08)]">
        <div className="relative z-10 grid gap-5 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
          <div>
            <p className="font-mono text-[0.68rem] font-semibold uppercase tracking-[0.24em] text-[#8f3148]">
              审计建议
            </p>
            <h2 className="mt-3 text-3xl font-black tracking-normal text-[#15130f]">
              {currentEnterprise ? `${currentEnterprise.name} 审计建议` : "审计建议"}
            </h2>
            {pageState.kind !== "ready" ? (
              <p className="mt-3 max-w-3xl text-sm font-semibold leading-6 text-[#5d503b]">{pageState.message}</p>
            ) : null}
          </div>
          <Button
            onClick={() => void handleRefreshAdvice()}
            disabled={!currentEnterpriseId || refreshingAdvice || focusLoading}
            className="min-h-11 bg-[#15130f] px-5 font-bold text-[#fffaf0] hover:bg-[#3f3628]"
          >
            {refreshingAdvice ? "刷新中..." : "刷新审计建议"}
          </Button>
          <div className="mt-5 rounded-2xl border border-[#1d1912]/10 bg-[#fffdf7]/88 p-4 lg:col-span-2">
            <p className="font-mono text-[0.68rem] font-bold uppercase tracking-[0.22em] text-[#8f3148]">
              总结
            </p>
            <p className="mt-2 text-sm font-semibold leading-6 text-[#5d503b]">{pageSummary}</p>
          </div>
        </div>
      </section>

      {pageState.kind === "loading" || pageState.kind === "empty" ? (
        <AdviceStateBox>{pageState.message}</AdviceStateBox>
      ) : pageState.kind === "error" ? (
        <AdviceStateBox tone="error">{pageState.message}</AdviceStateBox>
      ) : (
        <div className="space-y-4">
          {items.map((item, index) => {
            const matchedRisk = riskByTitle.get(item.title);
            const riskType = getRiskType(item, matchedRisk);
            const riskStatement = getRiskStatement(item, matchedRisk);
            const adviceSummary = compactText(item.targeted_advice ?? item.summary, "暂无建议概括。");
            const procedures = findExpandedItems(item, "建议程序");
            const evidenceToObtain = findExpandedItems(item, "需获取证据");

            return (
              <article
                key={item.id}
                className="audit-overview-panel relative overflow-hidden rounded-[28px] border border-[#1d1912]/10 px-5 py-5 text-[#15130f] shadow-[0_20px_55px_rgba(21,19,15,0.08)]"
              >
                <details className="group">
                  <summary className="list-none cursor-pointer">
                    <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#15130f] font-mono text-xs font-black text-[#fffaf0]">
                            {index + 1}
                          </span>
                          <p className="font-mono text-[0.68rem] font-bold uppercase tracking-[0.22em] text-[#8f3148]">
                            风险类型
                          </p>
                        </div>
                        <h3 className="mt-3 text-xl font-black leading-7 tracking-normal text-[#15130f]">{riskType}</h3>
                        <p className="mt-2 text-sm font-semibold leading-6 text-[#5d503b]">{riskStatement}</p>
                      </div>
                      <div className="rounded-2xl border border-[#1d1912]/10 bg-[#fffdf7]/88 p-4">
                        <p className="font-mono text-[0.68rem] font-bold uppercase tracking-[0.22em] text-[#8f3148]">
                          建议概括
                        </p>
                        <p className="mt-3 text-sm font-semibold leading-6 text-[#5d503b]">{adviceSummary}</p>
                      </div>
                    </div>
                  </summary>

                  <div className="mt-5 grid gap-4 border-t border-[#1d1912]/10 pt-5 lg:grid-cols-2">
                    <AdviceList title="建议程序" items={procedures} emptyText="暂无建议程序。" />
                    <AdviceList title="需获取证据" items={evidenceToObtain} emptyText="暂无需获取证据。" />
                  </div>
                </details>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}

function AdviceStateBox({
  tone = "muted",
  children,
}: {
  tone?: "muted" | "error";
  children: ReactNode;
}) {
  const className =
    tone === "error"
      ? "border-[#c94b35]/25 bg-[#c94b35]/10 text-[#8c2e22]"
      : "border-[#d8c8aa] bg-[#f8f3e8]/75 text-[#6c5d45]";

  return (
    <section className="audit-overview-panel rounded-[28px] border border-[#1d1912]/10 p-6 shadow-[0_20px_55px_rgba(21,19,15,0.08)]">
      <div className={`rounded-2xl border border-dashed px-5 py-5 text-sm font-semibold leading-6 ${className}`}>
        {children}
      </div>
    </section>
  );
}

function AdviceList({ title, items, emptyText }: { title: string; items: string[]; emptyText: string }) {
  return (
    <section className="rounded-2xl border border-[#1d1912]/10 bg-[#fffdf7]/88 p-4">
      <p className="font-mono text-[0.68rem] font-bold uppercase tracking-[0.22em] text-[#8f3148]">{title}</p>
      {items.length ? (
        <ol className="mt-3 space-y-2">
          {items.map((detail, index) => (
            <li key={`${detail}-${index}`} className="rounded-xl border border-[#1d1912]/10 bg-[#f8f3e8] px-4 py-3">
              <p className="text-sm font-semibold leading-6 text-[#5d503b]">
                <span className="mr-2 font-mono font-black text-[#15130f]">{index + 1}.</span>
                {detail}
              </p>
            </li>
          ))}
        </ol>
      ) : (
        <div className="mt-3 rounded-xl border border-dashed border-[#d8c8aa] bg-[#f8f3e8]/70 p-4 text-sm font-semibold text-[#6c5d45]">
          {emptyText}
        </div>
      )}
    </section>
  );
}

function buildRiskLookup(risks: RiskResultPayload[]): Map<string, RiskResultPayload> {
  const lookup = new Map<string, RiskResultPayload>();
  for (const risk of risks) {
    lookup.set(risk.risk_name, risk);
    if (risk.canonical_risk_key) {
      lookup.set(getRiskLabel(risk), risk);
    }
  }
  return lookup;
}

function buildAdviceSummary(items: FocusItem[], riskByTitle: Map<string, RiskResultPayload>): string {
  if (!items.length) {
    return "暂无建议。";
  }
  const riskTypes = items
    .map((item) => getRiskType(item, riskByTitle.get(item.title)))
    .filter((value, index, array) => value && array.indexOf(value) === index);
  const firstType = riskTypes[0] || "主要风险";
  return `共${items.length}条建议。覆盖${riskTypes.length}类风险。先处理${firstType}。`;
}

function getRiskType(item: FocusItem, risk?: RiskResultPayload): string {
  if (risk?.canonical_risk_key) {
    return getRiskLabel(risk);
  }
  return item.title;
}

function getRiskLabel(risk: RiskResultPayload): string {
  const mapped = risk.canonical_risk_key ? formatCanonicalRiskKey(risk.canonical_risk_key) : "";
  if (!isUnmappedLabel(mapped) && mapped !== "其他风险") {
    return mapped;
  }
  return risk.risk_name || "其他风险";
}

function getRiskStatement(item: FocusItem, risk?: RiskResultPayload): string {
  const firstReason = risk?.reasons?.find((reason) => reason.trim());
  return compactText(risk?.summary ?? risk?.llm_summary ?? firstReason ?? item.summary, "暂无风险概括。");
}

function findExpandedItems(item: FocusItem, title: string): string[] {
  return (
    item.expanded_sections?.find((section) => section.title.includes(title))?.items?.filter((detail) => detail.trim()) ??
    []
  );
}
