"use client";

import { useEffect, useState } from "react";
import type { AuditFocusPayload } from "@auditpilot/shared-types";

import { Card } from "@/components/ui/card";
import { api } from "@/lib/api";

function FocusBlock({ title, items }: { title: string; items: string[] }) {
  return (
    <Card>
      <p className="text-xs uppercase tracking-[0.24em] text-steel">{title}</p>
      <div className="mt-4 flex flex-wrap gap-3">
        {items.map((item) => (
          <span key={item} className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-haze/85">
            {item}
          </span>
        ))}
      </div>
    </Card>
  );
}

export default function AuditFocusPage() {
  const [focus, setFocus] = useState<AuditFocusPayload | null>(null);

  useEffect(() => {
    api.getAuditFocus(1).then(setFocus).catch(console.error);
  }, []);

  return (
    <div className="space-y-6 pb-10">
      <Card>
        <p className="text-xs uppercase tracking-[0.24em] text-steel">Audit Focus</p>
        <h2 className="mt-3 text-3xl font-semibold text-white">审计重点提示</h2>
        <p className="mt-2 text-haze/75">
          系统会把命中的风险自动映射到重点科目、流程、建议程序与应补充获取的证据类型。
        </p>
      </Card>
      <div className="grid gap-5 xl:grid-cols-2">
        <FocusBlock title="重点科目" items={focus?.focus_accounts ?? []} />
        <FocusBlock title="重点流程" items={focus?.focus_processes ?? []} />
        <FocusBlock title="建议审计程序" items={focus?.recommended_procedures ?? []} />
        <FocusBlock title="建议证据类型" items={focus?.evidence_types ?? []} />
      </div>
      <Card>
        <p className="text-xs uppercase tracking-[0.24em] text-steel">Narrative Recommendations</p>
        <div className="mt-4 space-y-3">
          {(focus?.recommendations ?? []).map((item) => (
            <div key={item} className="rounded-2xl border border-white/10 bg-white/5 p-4 text-haze/80">
              {item}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

