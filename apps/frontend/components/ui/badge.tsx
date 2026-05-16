import { cn } from "@/lib/utils";
import { formatRiskLevel } from "@/lib/display-labels";

const palette = {
  HIGH: "border-[#c94b35]/30 bg-[#c94b35]/10 text-[#8c2e22]",
  MEDIUM: "border-[#d6a65e]/35 bg-[#f4dfb9]/50 text-[#7a4b14]",
  LOW: "border-[#6c8a5d]/30 bg-[#edf3e8] text-[#4a673c]",
  rule: "border-[#15130f]/15 bg-[#f8f3e8] text-[#3f3628]",
  model: "border-[#8f3148]/25 bg-[#e24c74]/10 text-[#8f3148]",
  default: "border-[#d8c8aa] bg-[#f8f3e8] text-[#5d503b]",
};

export function Badge({ value, label }: { value: string; label?: string }) {
  const style = palette[value as keyof typeof palette] ?? palette.default;
  return (
    <span className={cn("inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-bold", style)}>
      {label ?? formatRiskLevel(value)}
    </span>
  );
}
