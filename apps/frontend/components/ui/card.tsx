import * as React from "react";

import { cn } from "@/lib/utils";

export function Card({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "audit-panel rounded-[28px] border border-[#1d1912]/10 p-6 text-[#15130f] shadow-soft",
        className,
      )}
      {...props}
    />
  );
}
