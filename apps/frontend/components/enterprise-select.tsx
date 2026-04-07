"use client";

import type { EnterpriseSummary } from "@auditpilot/shared-types";

export function EnterpriseSelect({
  enterprises,
  value,
  onChange,
}: {
  enterprises: EnterpriseSummary[];
  value: number;
  onChange: (enterpriseId: number) => void;
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(Number(event.target.value))}
      className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white outline-none transition focus:border-amber-400/50"
    >
      {enterprises.map((enterprise) => (
        <option key={enterprise.id} value={enterprise.id} className="bg-slate text-white">
          {enterprise.name} | {enterprise.ticker}
        </option>
      ))}
    </select>
  );
}

