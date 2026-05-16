import * as React from "react";

import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type = "text", ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      className={cn(
        "flex h-10 w-full rounded-xl border border-[#d8c8aa] bg-[#fffdf7]/85 px-3 py-2 text-sm font-semibold text-[#15130f] shadow-[inset_0_1px_0_rgba(255,255,255,0.82)] transition-colors file:border-0 file:bg-transparent file:text-sm file:font-semibold placeholder:text-[#8a7759] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#e24c74]/45 disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
);

Input.displayName = "Input";
