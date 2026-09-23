import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/**
 * Canonical status chip: neutral outline surface, the status word as the
 * accessible cue, and exactly one semantic dot marker (a theme-token class
 * from `@/lib/status-colors`). The surface and text are never tinted.
 */
export function StatusBadge({
  dotClass,
  className,
  children,
}: {
  dotClass: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Badge variant="outline" className={cn("gap-1.5", className)}>
      <span
        aria-hidden="true"
        className={cn("size-1.5 shrink-0 rounded-full", dotClass)}
      />
      {children}
    </Badge>
  );
}
