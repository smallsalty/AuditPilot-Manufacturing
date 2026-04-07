import { cn } from "@/lib/utils";

const palette = {
  HIGH: "bg-red-500/20 text-red-200 border-red-400/30",
  MEDIUM: "bg-amber-500/20 text-amber-100 border-amber-300/30",
  LOW: "bg-emerald-500/20 text-emerald-100 border-emerald-300/30",
  rule: "bg-sky-500/20 text-sky-100 border-sky-300/30",
  model: "bg-fuchsia-500/20 text-fuchsia-100 border-fuchsia-300/30",
  default: "bg-white/10 text-haze border-white/15",
};

export function Badge({ value }: { value: string }) {
  const style = palette[value as keyof typeof palette] ?? palette.default;
  return <span className={cn("rounded-full border px-3 py-1 text-xs font-medium", style)}>{value}</span>;
}

