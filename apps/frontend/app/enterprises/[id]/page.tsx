"use client";

import { useEffect, useMemo, useState } from "react";
import type {
  AuditProfilePayload,
  AuditTimelineItem,
  EnterpriseReadinessPayload,
  RiskSummaryPayload,
  SyncCompanyPayload,
} from "@auditpilot/shared-types";
import { useParams } from "next/navigation";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";
import {
  formatAnalysisStatus,
  formatExchange,
  formatSeverity,
  formatSourceName,
  formatStatus,
  formatSyncStatus,
  formatTimelineItemType,
} from "@/lib/display-labels";

type PageState = {
  profile: AuditProfilePayload | null;
  timeline: AuditTimelineItem[];
  riskSummary: RiskSummaryPayload | null;
  readiness: EnterpriseReadinessPayload | null;
  loading: boolean;
  error: string | null;
};

const initialState: PageState = {
  profile: null,
  timeline: [],
  riskSummary: null,
  readiness: null,
  loading: true,
  error: null,
};

export default function EnterpriseDetailPage() {
  const params = useParams<{ id: string }>();
  const enterpriseId = Number(params?.id);
  const { selectEnterprise } = useEnterpriseContext();
  const [state, setState] = useState<PageState>(initialState);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [syncSummary, setSyncSummary] = useState<SyncCompanyPayload | null>(null);

  useEffect(() => {
    if (Number.isFinite(enterpriseId)) {
      selectEnterprise(enterpriseId);
    }
  }, [enterpriseId, selectEnterprise]);

  const load = async () => {
    if (!Number.isFinite(enterpriseId)) {
      setState({ ...initialState, loading: false, error: "企业编号无效。" });
      return;
    }
    setState((current) => ({ ...current, loading: true, error: null }));
    try {
      const [profile, timeline, riskSummary, readiness] = await Promise.all([
        api.getAuditProfile(enterpriseId),
        api.getTimeline(enterpriseId),
        api.getRiskSummary(enterpriseId),
        api.getReadiness(enterpriseId),
      ]);
      setState({
        profile,
        timeline,
        riskSummary,
        readiness,
        loading: false,
        error: null,
      });
    } catch (error) {
      setState({
        profile: null,
        timeline: [],
        riskSummary: null,
        readiness: null,
        loading: false,
        error: error instanceof Error ? error.message : "审计概览加载失败。",
      });
    }
  };

  useEffect(() => {
    void load();
  }, [enterpriseId]);

  const triggerSync = async () => {
    if (!Number.isFinite(enterpriseId)) {
      return;
    }
    setSyncing(true);
    setSyncMessage(null);
    try {
      const result = await api.syncCompany(enterpriseId);
      setSyncSummary(result);
      setSyncMessage(
        `本次同步抓取公告 ${result.announcements_fetched} 条，新增文档 ${result.documents_inserted}/${result.documents_found} 条，新增事件 ${result.events_inserted}/${result.events_found} 条，待解析 ${result.parse_queued} 条。`,
      );
      await load();
    } catch (error) {
      setSyncSummary(null);
      setSyncMessage(error instanceof Error ? error.message : "同步失败。");
    } finally {
      setSyncing(false);
    }
  };

  const timelineItems = useMemo(() => state.timeline.slice(0, 20), [state.timeline]);

  return (
    <div className="space-y-6 pb-10">
      <Card>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-steel">企业审计概览</p>
            <h2 className="mt-3 text-3xl font-semibold text-white">
              {state.profile?.company.name ?? "企业审计概览"}
            </h2>
            <p className="mt-2 text-haze/75">
              {state.profile
                ? `${state.profile.company.ticker} | ${state.profile.company.industry_tag} | ${formatExchange(state.profile.company.exchange)}`
                : "查看企业主数据、公告时间线、监管信号和同步状态。"}
            </p>
            {syncMessage ? <p className="mt-3 text-sm text-amber-200">{syncMessage}</p> : null}
            {syncSummary && (syncSummary.warnings.length > 0 || syncSummary.errors.length > 0) ? (
              <div className="mt-3 space-y-2 text-sm">
                {syncSummary.warnings.map((item) => (
                  <p key={item} className="text-amber-100">
                    提示：{item}
                  </p>
                ))}
                {syncSummary.errors.map((item) => (
                  <p key={item} className="text-red-200">
                    错误：{item}
                  </p>
                ))}
              </div>
            ) : null}
          </div>
          <div className="flex gap-3">
            <Button variant="outline" onClick={() => void load()} disabled={state.loading || syncing}>
              刷新
            </Button>
            <Button onClick={triggerSync} disabled={syncing}>
              {syncing ? "同步中..." : "同步源数据"}
            </Button>
          </div>
        </div>
      </Card>

      {state.loading ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-haze/75">正在加载审计概览...</div>
        </Card>
      ) : state.error ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-5 text-sm text-red-100">{state.error}</div>
        </Card>
      ) : !state.profile ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-haze/75">当前企业暂无审计概览数据。</div>
        </Card>
      ) : (
        <>
          <section className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
            <Card>
              <p className="text-xs uppercase tracking-[0.24em] text-steel">同步状态</p>
              <p className="mt-3 text-2xl font-semibold text-white">
                {formatSyncStatus(state.readiness?.sync_status ?? state.profile.sync_status)}
              </p>
              <p className="mt-2 text-sm text-haze/75">
                最近同步：{state.readiness?.last_sync_at ?? state.profile.latest_sync_at ?? "尚未同步"}
              </p>
            </Card>
            <Card>
              <p className="text-xs uppercase tracking-[0.24em] text-steel">官方文档</p>
              <p className="mt-3 text-2xl font-semibold text-white">
                {state.readiness?.official_doc_count ?? state.profile.document_count}
              </p>
              <p className="mt-2 text-sm text-haze/75">最近文档：{state.profile.latest_document_date ?? "暂无"}</p>
            </Card>
            <Card>
              <p className="text-xs uppercase tracking-[0.24em] text-steel">监管事件</p>
              <p className="mt-3 text-2xl font-semibold text-white">
                {state.readiness?.official_event_count ?? state.profile.penalty_count}
              </p>
              <p className="mt-2 text-sm text-haze/75">最近事件：{state.profile.latest_penalty_date ?? "暂无"}</p>
            </Card>
            <Card>
              <p className="text-xs uppercase tracking-[0.24em] text-steel">风险分析状态</p>
              <p className="mt-3 text-2xl font-semibold text-white">
                {formatAnalysisStatus(state.readiness?.risk_analysis_status ?? state.profile.data_sources?.risk_analysis_status)}
              </p>
              <p className="mt-2 text-sm text-haze/75">问答可用：{state.readiness?.qa_ready ? "是" : "否"}</p>
            </Card>
          </section>

          <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
            <Card>
              <p className="text-xs uppercase tracking-[0.24em] text-steel">企业主数据</p>
              <div className="mt-4 space-y-3 text-sm text-haze/80">
                <p>企业名称：{state.profile.company.name}</p>
                <p>股票代码：{state.profile.company.ticker}</p>
                <p>行业：{state.profile.company.industry_tag}</p>
                <p>交易所：{formatExchange(state.profile.company.exchange)}</p>
                <p>
                  所在地：{state.profile.company.province ?? "--"} / {state.profile.company.city ?? "--"}
                </p>
                <p>上市日期：{state.profile.company.listed_date ?? "--"}</p>
                <p className="pt-2 text-haze/70">{state.profile.company.description ?? "暂无企业描述。"}</p>
              </div>
            </Card>

            <Card>
              <p className="text-xs uppercase tracking-[0.24em] text-steel">数据来源与状态</p>
              <div className="mt-4 space-y-3 text-sm text-haze/80">
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  企业主数据来源：{formatSourceName(state.profile.data_sources?.profile ?? "akshare_fast")}
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  公告与文档来源：{formatSourceName(state.profile.data_sources?.documents ?? "cninfo / upload")}
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  事件来源：{formatSourceName(state.profile.data_sources?.events ?? "cninfo / upload")}
                </div>
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  当前风险分析状态：{formatAnalysisStatus(state.profile.data_sources?.risk_analysis_status)}
                </div>
              </div>
            </Card>
          </section>

          <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
            <Card>
              <p className="text-xs uppercase tracking-[0.24em] text-steel">时间线</p>
              {timelineItems.length > 0 ? (
                <div className="mt-4 space-y-3">
                  {timelineItems.map((item) => (
                    <div key={item.id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <p className="font-medium text-white">{item.title}</p>
                        <span className="text-xs uppercase tracking-[0.2em] text-steel">
                          {formatTimelineItemType(item.item_type)} | {item.date ?? "未知日期"}
                        </span>
                      </div>
                      <p className="mt-2 text-sm text-haze/75">{item.summary}</p>
                      <p className="mt-2 text-xs text-steel">
                        {formatSourceName(item.source)} | {formatStatus(item.status)}
                        {item.severity ? ` | ${formatSeverity(item.severity)}` : ""}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
                  当前暂无官方文档或监管事件时间线。
                </div>
              )}
            </Card>

            <Card>
              <p className="text-xs uppercase tracking-[0.24em] text-steel">风险摘要</p>
              {state.riskSummary ? (
                <div className="mt-4 space-y-3">
                  {state.riskSummary.highlights.length ? (
                    state.riskSummary.highlights.map((item) => (
                      <div key={item} className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/80">
                        {item}
                      </div>
                    ))
                  ) : (
                    <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
                      当前暂无可展示的风险摘要。
                    </div>
                  )}
                </div>
              ) : (
                <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
                  当前暂无结构化风险摘要。
                </div>
              )}
            </Card>
          </section>
        </>
      )}
    </div>
  );
}
