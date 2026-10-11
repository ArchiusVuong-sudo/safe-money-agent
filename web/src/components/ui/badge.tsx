import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";
import { cn } from "../../lib/cn";

const badgeVariants = cva("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap", {
  variants: {
    variant: {
      neutral: "bg-slate-100 text-slate-700",
      outline: "border border-slate-200 bg-white text-slate-700",
      good: "bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-600/20",
      bad: "bg-rose-50 text-rose-700 ring-1 ring-inset ring-rose-600/20",
      warn: "bg-amber-50 text-amber-800 ring-1 ring-inset ring-amber-600/25",
      info: "bg-sky-50 text-sky-700 ring-1 ring-inset ring-sky-600/20",
      brand: "bg-brand-50 text-brand-700 ring-1 ring-inset ring-brand-600/20",
    },
  },
  defaultVariants: { variant: "neutral" },
});

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
