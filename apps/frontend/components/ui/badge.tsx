import { cn } from "@/lib/utils";
import { formatRiskLevel } from "@/lib/display-labels";

const palette = {
  HIGH: "border-red-200 bg-red-50 text-red-700",
  MEDIUM: "border-amber-200 bg-amber-50 text-amber-700",
  LOW: "border-emerald-200 bg-emerald-50 text-emerald-700",
  rule: "border-blue-200 bg-blue-50 text-blue-700",
  model: "border-violet-200 bg-violet-50 text-violet-700",
  default: "border-border bg-muted text-muted-foreground",
};

export function Badge({ value, label }: { value: string; label?: string }) {
  const style = palette[value as keyof typeof palette] ?? palette.default;
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium", style)}>
      {label ?? formatRiskLevel(value)}
    </span>
  );
}
