import * as React from "react";

import { cn } from "@/lib/utils";

type ButtonVariant = "default" | "ghost" | "outline" | "secondary" | "destructive";

export function Button({
  className,
  variant = "default",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button
      className={cn(
        "inline-flex h-10 items-center justify-center rounded-lg px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        variant === "default" && "bg-primary text-primary-foreground hover:bg-primary/90",
        variant === "secondary" && "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        variant === "ghost" && "text-foreground hover:bg-muted",
        variant === "outline" && "border border-input bg-background text-foreground hover:bg-muted",
        variant === "destructive" && "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        "disabled:pointer-events-none disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
