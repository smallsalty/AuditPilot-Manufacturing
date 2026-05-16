import * as React from "react";

import { cn } from "@/lib/utils";

type ButtonVariant = "default" | "ghost" | "outline" | "secondary" | "destructive";

export const Button = React.forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }
>(({ className, variant = "default", ...props }, ref) => (
    <button
      ref={ref}
      className={cn(
        "audit-hover-lift inline-flex h-10 items-center justify-center rounded-full px-4 py-2 text-sm font-bold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        variant === "default" && "border border-[#15130f] bg-[#15130f] text-[#fffaf0] shadow-[6px_6px_0_rgba(226,76,116,0.24)] hover:bg-[#3f3628]",
        variant === "secondary" && "border border-[#d8c8aa] bg-[#f8f3e8] text-[#3f3628] hover:border-[#15130f]/25 hover:bg-[#fffdf7]",
        variant === "ghost" && "text-[#3f3628] hover:bg-[#f8f3e8]/80 hover:text-[#15130f]",
        variant === "outline" && "border border-[#15130f]/25 bg-[#fffaf0]/45 text-[#15130f] hover:border-[#15130f]/55 hover:bg-[#fffdf7]",
        variant === "destructive" && "border border-[#c94b35] bg-[#c94b35] text-[#fffaf0] hover:bg-[#8c2e22]",
        "disabled:pointer-events-none disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
);

Button.displayName = "Button";
