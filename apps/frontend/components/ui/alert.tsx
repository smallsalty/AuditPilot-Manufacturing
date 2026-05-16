import * as React from "react";

import { cn } from "@/lib/utils";

export function Alert({
  className,
  variant = "default",
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { variant?: "default" | "destructive" | "warning" }) {
  return (
    <div
      role="alert"
      className={cn(
        "relative w-full rounded-2xl border px-4 py-3 text-sm font-semibold shadow-[inset_0_1px_0_rgba(255,255,255,0.72)]",
        variant === "default" && "border-[#d8c8aa] bg-[#f8f3e8]/75 text-[#5d503b]",
        variant === "destructive" && "border-[#c94b35]/25 bg-[#c94b35]/10 text-[#8c2e22]",
        variant === "warning" && "border-[#d6a65e]/35 bg-[#f4dfb9]/45 text-[#7a4b14]",
        className,
      )}
      {...props}
    />
  );
}

export function AlertTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h5 className={cn("font-black leading-none tracking-normal text-[#15130f]", className)} {...props} />;
}

export function AlertDescription({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mt-1.5 text-sm leading-6", className)} {...props} />;
}
