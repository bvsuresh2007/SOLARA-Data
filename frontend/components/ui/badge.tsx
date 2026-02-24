import { cn } from "@/lib/utils";

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "success" | "warning" | "danger" | "muted";
}

const variants: Record<NonNullable<BadgeProps["variant"]>, string> = {
  default: "bg-zinc-800 text-zinc-200",
  success: "bg-green-900/50 text-green-400 border border-green-800",
  warning: "bg-yellow-900/50 text-yellow-400 border border-yellow-800",
  danger:  "bg-red-900/50 text-red-400 border border-red-800",
  muted:   "bg-zinc-800 text-zinc-500",
};

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
