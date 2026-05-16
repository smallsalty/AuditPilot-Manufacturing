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
      className="w-full rounded-xl border border-[#d8c8aa] bg-[#fffdf7]/85 px-4 py-3 text-sm font-semibold text-[#15130f] outline-none transition focus:ring-2 focus:ring-[#e24c74]/45"
    >
      {enterprises.map((enterprise) => (
        <option key={enterprise.id} value={enterprise.id}>
          {enterprise.name} | {enterprise.ticker}
        </option>
      ))}
    </select>
  );
}
