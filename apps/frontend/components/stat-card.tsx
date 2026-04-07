import { Card } from "@/components/ui/card";

export function StatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint: string;
}) {
  return (
    <Card className="overflow-hidden">
      <p className="text-sm text-haze/70">{label}</p>
      <div className="mt-4 flex items-end justify-between gap-4">
        <span className="text-4xl font-semibold tracking-tight text-white">{value}</span>
        <span className="rounded-full bg-white/5 px-3 py-1 text-xs text-haze/70">{hint}</span>
      </div>
    </Card>
  );
}

