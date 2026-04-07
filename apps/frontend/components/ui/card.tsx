import * as React from "react";

import { cn } from "@/lib/utils";

export function Card({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-3xl border border-white/10 bg-slate/85 p-6 shadow-soft backdrop-blur-sm",
        className,
      )}
      {...props}
    />
  );
}

