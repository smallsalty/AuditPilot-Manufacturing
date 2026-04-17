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
      <p className="text-sm text-muted-foreground">{label}</p>
      <div className="mt-4 flex items-end justify-between gap-4">
        <span className="text-4xl font-semibold tracking-tight text-foreground">{value}</span>
        <span className="rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground">{hint}</span>
      </div>
    </Card>
  );
}
