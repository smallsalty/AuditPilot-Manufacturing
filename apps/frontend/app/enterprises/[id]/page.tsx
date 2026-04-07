"use client";

import { useEffect, useState } from "react";
import type { EnterpriseDetail } from "@auditpilot/shared-types";

import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";

export default function EnterpriseDetailPage({ params }: { params: { id: string } }) {
  const [detail, setDetail] = useState<EnterpriseDetail | null>(null);

  useEffect(() => {
    api.getEnterprise(Number(params.id)).then(setDetail).catch(console.error);
  }, [params.id]);

  return (
    <div className="space-y-6 pb-10">
      <Card>
        <p className="text-xs uppercase tracking-[0.24em] text-steel">Enterprise Profile</p>
        <h2 className="mt-3 text-3xl font-semibold text-white">{detail?.name ?? "企业详情"}</h2>
        <p className="mt-2 text-haze/75">
          {detail?.ticker} | {detail?.industry_tag} | {detail?.sub_industry}
        </p>
        <p className="mt-4 max-w-4xl text-haze/75">{detail?.description}</p>
      </Card>

      <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <p className="text-xs uppercase tracking-[0.24em] text-steel">核心财务指标</p>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-sm text-haze/85">
              <thead>
                <tr className="text-left text-steel">
                  <th className="pb-3">期间</th>
                  <th className="pb-3">类型</th>
                  <th className="pb-3">指标</th>
                  <th className="pb-3">数值</th>
                </tr>
              </thead>
              <tbody>
                {(detail?.financial_metrics ?? []).map((metric) => (
                  <tr key={`${metric.report_period}-${metric.indicator_code}`} className="border-t border-white/10">
                    <td className="py-3">{metric.report_period}</td>
                    <td className="py-3">{metric.period_type}</td>
                    <td className="py-3">{metric.indicator_name}</td>
                    <td className="py-3">{metric.value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
        <Card>
          <p className="text-xs uppercase tracking-[0.24em] text-steel">外部风险事件</p>
          <div className="mt-4 space-y-3">
            {(detail?.external_events ?? []).map((event) => (
              <div key={event.id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <p className="font-medium text-white">{event.title}</p>
                <p className="mt-1 text-xs uppercase tracking-[0.2em] text-steel">
                  {event.event_type} | {event.severity} | {event.event_date ?? "无日期"}
                </p>
                <p className="mt-2 text-haze/75">{event.summary}</p>
              </div>
            ))}
          </div>
        </Card>
      </section>
    </div>
  );
}
