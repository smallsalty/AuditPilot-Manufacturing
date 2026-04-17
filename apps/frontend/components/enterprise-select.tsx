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
      className="w-full rounded-lg border border-input bg-background px-4 py-3 text-sm text-foreground outline-none transition focus:ring-2 focus:ring-ring"
    >
      {enterprises.map((enterprise) => (
        <option key={enterprise.id} value={enterprise.id}>
          {enterprise.name} | {enterprise.ticker}
        </option>
      ))}
    </select>
  );
}
