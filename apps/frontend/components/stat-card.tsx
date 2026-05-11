export function StatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint: string;
}) {
  const numericValue = typeof value === "number" && Number.isFinite(value) ? Math.round(value) : null;
  const meterValue = numericValue === null ? 14 : Math.min(Math.max(numericValue, 8), 100);

  return (
    <div className="relative overflow-hidden rounded-2xl border border-[#1d1912]/10 bg-[#fffdf7] p-5 text-[#15130f] shadow-[0_18px_40px_rgba(21,19,15,0.08)]">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-1 bg-[linear-gradient(90deg,#15130f,#c94b35,#e24c74)]" />
      <div className="flex items-start justify-between gap-4">
        <p className="text-sm font-semibold text-[#5d503b]">{label}</p>
        <span className="rounded-full border border-[#d8c8aa] bg-[#f3efe4] px-3 py-1 text-[0.68rem] font-semibold text-[#6c5d45]">
          {hint}
        </span>
      </div>
      <div className="mt-7 flex items-end justify-between gap-5">
        <div>
          <span
            className={
              numericValue === null
                ? "text-3xl font-black leading-none tracking-normal text-[#15130f]"
                : "font-mono text-[3.2rem] font-black leading-none tracking-normal text-[#15130f]"
            }
          >
            {numericValue ?? "待测"}
          </span>
          <span className="ml-1 align-super text-xs font-bold text-[#c94b35]">{numericValue === null ? "" : "分"}</span>
        </div>
        <div className="mb-2 h-16 w-7 overflow-hidden rounded-full border border-[#15130f]/15 bg-[#f3efe4] p-1">
          <div className="flex h-full items-end rounded-full bg-[#d8c8aa]">
            <div className="w-full rounded-full bg-[#c94b35]" style={{ height: `${meterValue}%` }} />
          </div>
        </div>
      </div>
    </div>
  );
}
