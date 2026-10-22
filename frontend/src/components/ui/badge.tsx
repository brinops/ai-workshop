import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";
import { cn } from "@/lib/utils";

export const badgeVariants = cva(
  "inline-flex items-center gap-1 whitespace-nowrap rounded-[5px] border px-1.5 py-px text-[0.72rem] font-medium leading-5 [&_svg]:size-3 [&_svg]:shrink-0",
  {
    variants: {
      tone: {
        neutral: "border-line-strong/70 bg-raised text-muted",
        info: "border-accent/30 bg-accent/10 text-accent",
        accent: "border-accent/40 bg-accent/15 text-accent",
        success: "border-ok/35 bg-ok/10 text-ok",
        warning: "border-warn/40 bg-warn/10 text-warn",
        danger: "border-bad/40 bg-bad/10 text-bad",
        amber: "border-amber/40 bg-amber/10 text-amber",
        violet: "border-violet/40 bg-violet/10 text-violet",
        cyan: "border-cyan/40 bg-cyan/10 text-cyan",
        gray: "border-gray/35 bg-gray/10 text-gray",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
