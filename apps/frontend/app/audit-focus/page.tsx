"use client";

import { useMemo } from "react";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { Card } from "@/components/ui/card";
import { useAuditFocusResource, useDashboardResource } from "@/lib/enterprise-resources";

function FocusBlock({ title, items }: { title: string; items: string[] }) {
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
        <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">暂无数据</div>
      )}
    </Card>
  );
}

export default function AuditFocusPage() {
  const { currentEnterprise, currentEnterpriseId, enterpriseError } = useEnterpriseContext();
  const { data: dashboard, loading: dashboardLoading, error: dashboardError } = useDashboardResource(currentEnterpriseId);
  const { data: focus, loading: focusLoading, error: focusError } = useAuditFocusResource(currentEnterpriseId);

  const title = useMemo(() => {
    if (!currentEnterprise) return "审计重点提示";
    return `${currentEnterprise.name} 审计重点提示`;
  }, [currentEnterprise]);

  const analysisStatus = focus?.analysis_status ?? dashboard?.analysis_status ?? "not_started";

  return (
    <div className="space-y-6 pb-10">
      <Card>
        <p className="text-xs uppercase tracking-[0.24em] text-steel">Audit Focus</p>
        <h2 className="mt-3 text-3xl font-semibold text-white">{title}</h2>
        <p className="mt-2 text-haze/75">系统会把命中的风险自动映射到重点科目、流程、建议程序与应补充获取的证据类型。</p>
      </Card>

      {enterpriseError ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-5 text-sm text-red-100">
            企业列表加载失败：{enterpriseError}
          </div>
        </Card>
      ) : !currentEnterpriseId ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-haze/75">请先选择企业。</div>
        </Card>
      ) : dashboardLoading || focusLoading ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-haze/75">正在加载审计重点...</div>
        </Card>
      ) : dashboardError ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-5 text-sm text-red-100">
            总览数据加载失败：{dashboardError}
          </div>
        </Card>
      ) : analysisStatus === "not_started" ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-haze/75">
            当前企业尚未运行风险分析，请先执行分析任务。
          </div>
        </Card>
      ) : analysisStatus === "running" ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-haze/75">
            风险分析正在执行中，审计重点将在完成后自动生成。
          </div>
        </Card>
      ) : analysisStatus === "failed" ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-5 text-sm text-red-100">
            风险分析失败：{focus?.last_error ?? dashboard?.last_error ?? "请重试风险分析。"}
          </div>
        </Card>
      ) : focusError ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-5 text-sm text-red-100">
            审计重点加载失败：{focusError}
          </div>
        </Card>
      ) : (
        <>
          <div className="grid gap-5 xl:grid-cols-2">
            <FocusBlock title="重点科目" items={focus?.focus_accounts ?? []} />
            <FocusBlock title="重点流程" items={focus?.focus_processes ?? []} />
            <FocusBlock title="建议审计程序" items={focus?.recommended_procedures ?? []} />
            <FocusBlock title="建议证据类型" items={focus?.evidence_types ?? []} />
          </div>
          <Card>
            <p className="text-xs uppercase tracking-[0.24em] text-steel">Narrative Recommendations</p>
            {focus?.recommendations?.length ? (
              <div className="mt-4 space-y-3">
                {focus.recommendations.map((item) => (
                  <div key={item} className="rounded-2xl border border-white/10 bg-white/5 p-4 text-haze/80">
                    {item}
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
                当前企业暂无可展示的审计重点建议。
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
