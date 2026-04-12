"use client";

import { useEffect, useMemo, useState } from "react";
import type {
  AuditProfilePayload,
  AuditTimelineItem,
  RiskSummaryPayload,
  SyncCompanyPayload,
} from "@auditpilot/shared-types";

import { useEnterpriseContext } from "@/components/enterprise-provider";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";

type PageState = {
  profile: AuditProfilePayload | null;
  timeline: AuditTimelineItem[];
  riskSummary: RiskSummaryPayload | null;
  loading: boolean;
  error: string | null;
};

const initialState: PageState = {
  profile: null,
  timeline: [],
  riskSummary: null,
  loading: true,
  error: null,
};

export default function EnterpriseDetailPage({ params }: { params: { id: string } }) {
  const enterpriseId = Number(params.id);
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
      setState({ ...initialState, loading: false, error: "Invalid enterprise id." });
      return;
    }
    setState((current) => ({ ...current, loading: true, error: null }));
    try {
      const [profile, timeline, riskSummary] = await Promise.all([
        api.getAuditProfile(enterpriseId),
        api.getTimeline(enterpriseId),
        api.getRiskSummary(enterpriseId),
      ]);
      setState({
        profile,
        timeline,
        riskSummary,
        loading: false,
        error: null,
      });
    } catch (error) {
      setState({
        profile: null,
        timeline: [],
        riskSummary: null,
        loading: false,
        error: error instanceof Error ? error.message : "Failed to load audit overview.",
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
      const result: SyncCompanyPayload = await api.syncCompany(enterpriseId);
      setSyncSummary(result);
      setSyncMessage(
        `Profile updated: ${result.company_profile_updated ? "yes" : "no"}, announcements ${result.announcements_fetched}, documents ${result.documents_inserted}/${result.documents_found}, events ${result.events_inserted}/${result.events_found}, parse queued ${result.parse_queued}.`,
      );
      await load();
    } catch (error) {
      setSyncSummary(null);
      setSyncMessage(error instanceof Error ? error.message : "Sync failed.");
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
            <p className="text-xs uppercase tracking-[0.24em] text-steel">Audit Overview</p>
            <h2 className="mt-3 text-3xl font-semibold text-white">
              {state.profile?.company.name ?? "Company audit overview"}
            </h2>
            <p className="mt-2 text-haze/75">
              {state.profile
                ? `${state.profile.company.ticker} | ${state.profile.company.industry_tag} | ${state.profile.company.exchange}`
                : "Profile, reports, regulatory signals, and sync status."}
            </p>
            {syncMessage ? <p className="mt-3 text-sm text-amber-200">{syncMessage}</p> : null}
            {syncSummary && (syncSummary.warnings.length > 0 || syncSummary.errors.length > 0) ? (
              <div className="mt-3 space-y-2 text-sm">
                {syncSummary.warnings.map((item) => (
                  <p key={item} className="text-amber-100">
                    Warning: {item}
                  </p>
                ))}
                {syncSummary.errors.map((item) => (
                  <p key={item} className="text-red-200">
                    Error: {item}
                  </p>
                ))}
              </div>
            ) : null}
          </div>
          <div className="flex gap-3">
            <Button variant="outline" onClick={() => void load()} disabled={state.loading || syncing}>
              Refresh
            </Button>
            <Button onClick={triggerSync} disabled={syncing}>
              {syncing ? "Syncing..." : "Sync source data"}
            </Button>
          </div>
        </div>
      </Card>

      {state.loading ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-haze/75">
            Loading audit overview...
          </div>
        </Card>
      ) : state.error ? (
        <Card>
          <div className="rounded-2xl border border-red-400/20 bg-red-500/10 p-5 text-sm text-red-100">
            {state.error}
          </div>
        </Card>
      ) : !state.profile ? (
        <Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-haze/75">
            No audit overview data is available for this enterprise.
          </div>
        </Card>
      ) : (
        <>
          <section className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
            <Card>
              <p className="text-xs uppercase tracking-[0.24em] text-steel">Sync Status</p>
              <p className="mt-3 text-2xl font-semibold text-white">{state.profile.sync_status}</p>
              <p className="mt-2 text-sm text-haze/75">Latest sync: {state.profile.latest_sync_at ?? "not synced"}</p>
            </Card>
            <Card>
              <p className="text-xs uppercase tracking-[0.24em] text-steel">Audit Reports</p>
              <p className="mt-3 text-2xl font-semibold text-white">{state.profile.document_count}</p>
              <p className="mt-2 text-sm text-haze/75">Latest: {state.profile.latest_document_date ?? "n/a"}</p>
            </Card>
            <Card>
              <p className="text-xs uppercase tracking-[0.24em] text-steel">Regulatory Signals</p>
              <p className="mt-3 text-2xl font-semibold text-white">{state.profile.penalty_count}</p>
              <p className="mt-2 text-sm text-haze/75">Latest: {state.profile.latest_penalty_date ?? "n/a"}</p>
            </Card>
            <Card>
              <p className="text-xs uppercase tracking-[0.24em] text-steel">Official Source</p>
              <p className="mt-3 text-2xl font-semibold text-white">{state.profile.is_official_source ? "Yes" : "No"}</p>
              <p className="mt-2 text-sm text-haze/75">Priority: {state.profile.source_priority}</p>
            </Card>
          </section>

          <section className="grid gap-6 xl:grid-cols-[1fr_1fr]">
            <Card>
              <p className="text-xs uppercase tracking-[0.24em] text-steel">Company Profile</p>
              <div className="mt-4 space-y-3 text-sm text-haze/80">
                <p>Name: {state.profile.company.name}</p>
                <p>Ticker: {state.profile.company.ticker}</p>
                <p>Industry: {state.profile.company.industry_tag}</p>
                <p>
                  Region: {state.profile.company.province ?? "--"} / {state.profile.company.city ?? "--"}
                </p>
                <p>Listed date: {state.profile.company.listed_date ?? "--"}</p>
                <p className="pt-2 text-haze/70">{state.profile.company.description ?? "No company description yet."}</p>
              </div>
            </Card>
            <Card>
              <p className="text-xs uppercase tracking-[0.24em] text-steel">Risk Summary</p>
              {state.riskSummary ? (
                <div className="mt-4 space-y-3">
                  {state.riskSummary.highlights.map((item) => (
                    <div key={item} className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/80">
                      {item}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
                  No summary metrics are available.
                </div>
              )}
            </Card>
          </section>

          <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
            <Card>
              <p className="text-xs uppercase tracking-[0.24em] text-steel">Timeline</p>
              {timelineItems.length > 0 ? (
                <div className="mt-4 space-y-3">
                  {timelineItems.map((item) => (
                    <div key={item.id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <p className="font-medium text-white">{item.title}</p>
                        <span className="text-xs uppercase tracking-[0.2em] text-steel">
                          {item.item_type} | {item.date ?? "n/a"}
                        </span>
                      </div>
                      <p className="mt-2 text-sm text-haze/75">{item.summary}</p>
                      <p className="mt-2 text-xs text-steel">
                        {item.source} | {item.status}
                        {item.severity ? ` | ${item.severity}` : ""}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
                  No reports or regulatory events are stored yet.
                </div>
              )}
            </Card>
            <Card>
              <p className="text-xs uppercase tracking-[0.24em] text-steel">Structured Metrics</p>
              {state.riskSummary ? (
                <div className="mt-4 space-y-3 text-sm text-haze/80">
                  <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    Document count: {state.riskSummary.document_count}
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    Official documents: {state.riskSummary.official_document_count}
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    Penalty count: {state.riskSummary.penalty_count}
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    High severity penalties: {state.riskSummary.high_severity_penalty_count}
                  </div>
                </div>
              ) : (
                <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-haze/75">
                  No structured metrics are available.
                </div>
              )}
            </Card>
          </section>
        </>
      )}
    </div>
  );
}
