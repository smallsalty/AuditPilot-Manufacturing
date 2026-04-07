import * as React from "react";

import { cn } from "@/lib/utils";

export function Button({
  className,
  variant = "default",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "default" | "ghost" | "outline" }) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center rounded-full px-4 py-2 text-sm font-semibold transition",
        variant === "default" && "bg-ember text-white hover:bg-amber-600",
        variant === "ghost" && "bg-white/5 text-haze hover:bg-white/10",
        variant === "outline" && "border border-white/20 bg-transparent text-haze hover:bg-white/5",
        "disabled:cursor-not-allowed disabled:opacity-60",
        className,
      )}
      {...props}
    />
  );
}

