"use client";

import { ArrowRight, CheckCircle2, Circle, PartyPopper, Rocket, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useSetupChecklist } from "@/hooks/useSetupChecklist";
import { cn } from "@/lib/utils";

interface SetupChecklistProps {
  /** When provided, renders a header X that hides the card (and persists it). */
  onDismiss?: () => void;
  className?: string;
}

/**
 * The persistent "Finish setup" card: 5 checkable steps, each backed by live
 * workspace state (no optimistic/fake completion) and each linking straight to
 * its own screen. Shows visible progress while incomplete and a celebration
 * (banner + toast + dashboard CTA) once every step checks off.
 *
 * Used full-page at `/onboarding` (the reused `setupNavItem` entry point) and
 * as a dismissible banner at the top of the app shell via `SetupGate`.
 */
export function SetupChecklist({ onDismiss, className }: SetupChecklistProps) {
  const { isLoading, isError, steps, completedCount, total, allComplete } =
    useSetupChecklist();

  // Fire the celebration toast only when the count actually advances to the
  // finish line while mounted — not on every mount of an already-complete card.
  const previousCompletedCount = useRef<number | null>(null);
  useEffect(() => {
    if (isLoading) return;
    if (previousCompletedCount.current === null) {
      previousCompletedCount.current = completedCount;
      return;
    }
    if (allComplete && completedCount > previousCompletedCount.current) {
      toast.success("Setup complete — you're all set!", { id: "setup-complete" });
    }
    previousCompletedCount.current = completedCount;
  }, [isLoading, completedCount, allComplete]);

  // Failed probes mean we cannot prove which steps are done — show nothing
  // rather than mis-state progress (callers hide on error too).
  if (isError) return null;

  if (isLoading) {
    return (
      <section
        aria-label="Finish setup checklist"
        className={cn("space-y-4 rounded-xl border bg-card p-6 shadow-sm", className)}
      >
        <div className="space-y-2">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-2 w-full" />
        </div>
        <div className="space-y-3">
          {Array.from({ length: total || 5 }, (_, index) => (
            <Skeleton key={index} className="h-10 w-full" />
          ))}
        </div>
      </section>
    );
  }

  const percentage = total > 0 ? Math.round((completedCount / total) * 100) : 0;

  return (
    <section
      aria-label="Finish setup checklist"
      className={cn("overflow-hidden rounded-xl border bg-card shadow-sm", className)}
    >
      <div
        className={cn(
          "border-b px-6 py-5",
          allComplete
            ? "bg-gradient-to-r from-emerald-500/10 to-green-600/10"
            : "bg-gradient-to-r from-violet-500/10 to-purple-600/10",
        )}
      >
        <div className="flex items-start gap-4">
          <div
            className={cn(
              "flex size-10 shrink-0 items-center justify-center rounded-xl text-white shadow-sm",
              allComplete
                ? "bg-gradient-to-br from-emerald-500 to-green-600"
                : "bg-gradient-to-br from-violet-500 to-purple-600",
            )}
            aria-hidden="true"
          >
            {allComplete ? (
              <PartyPopper className="size-5" />
            ) : (
              <Rocket className="size-5" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-semibold">
              {allComplete ? "You're all set!" : "Finish setup"}
            </p>
            <p className="text-sm text-muted-foreground">
              {allComplete
                ? "Every step is checked off — your workspace is ready to run."
                : "Complete these steps to get The Tribunal running your sales floor."}
            </p>
          </div>
          {onDismiss && (
            <Button
              variant="ghost"
              size="icon"
              onClick={onDismiss}
              aria-label="Dismiss setup checklist"
            >
              <X className="size-4" />
            </Button>
          )}
        </div>

        <div className="mt-4 space-y-1.5">
          <div className="flex items-center justify-between text-xs">
            <span className="font-medium">
              {completedCount} of {total} complete
            </span>
            <span className="text-muted-foreground">{percentage}%</span>
          </div>
          <Progress
            value={percentage}
            aria-label={`Setup progress: ${completedCount} of ${total} complete`}
            className={cn(
              allComplete && "[&_[data-slot=progress-indicator]]:bg-emerald-500",
            )}
          />
        </div>
      </div>

      <ul className="divide-y divide-border px-2 py-1">
        {steps.map((step) => (
          <li key={step.id}>
            <Link
              href={step.href}
              className="group flex items-center gap-3 rounded-lg px-4 py-3 transition-colors hover:bg-muted/50"
            >
              {step.done ? (
                <CheckCircle2
                  className="size-5 shrink-0 text-emerald-500"
                  aria-hidden="true"
                />
              ) : (
                <Circle className="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
              )}
              <span className="min-w-0 flex-1">
                <span
                  className={cn(
                    "block text-sm",
                    step.done ? "text-muted-foreground" : "font-medium",
                  )}
                >
                  {step.title}
                  <span className="sr-only">{step.done ? " (complete)" : " (todo)"}</span>
                </span>
                <span className="block text-xs text-muted-foreground">
                  {step.description}
                </span>
              </span>
              <ArrowRight
                className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
                aria-hidden="true"
              />
            </Link>
          </li>
        ))}
      </ul>

      {allComplete && (
        <div className="border-t px-6 py-4">
          <Button asChild size="sm">
            <Link href="/today">
              Go to Today
              <ArrowRight className="ml-2 size-4" aria-hidden="true" />
            </Link>
          </Button>
        </div>
      )}
    </section>
  );
}
