"use client";

import {
  ArrowRight,
  CheckCircle2,
  Circle,
  CircleHelp,
  PartyPopper,
  RefreshCw,
  Rocket,
  TriangleAlert,
  X,
} from "lucide-react";
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
  const {
    isLoading,
    isError,
    isRetrying,
    retry,
    steps,
    completedCount,
    unknownCount,
    total,
    allComplete,
  } = useSetupChecklist();

  // Fire the celebration toast only when the count actually advances to the
  // finish line while mounted — not on every mount of an already-complete card.
  // Counts are only compared once every step is known, so a retry that merely
  // reveals already-finished steps is not mistaken for finishing setup.
  const previousCompletedCount = useRef<number | null>(null);
  useEffect(() => {
    if (isLoading || unknownCount > 0) return;
    if (previousCompletedCount.current === null) {
      previousCompletedCount.current = completedCount;
      return;
    }
    if (allComplete && completedCount > previousCompletedCount.current) {
      toast.success("Setup complete, you're all set!", { id: "setup-complete" });
    }
    previousCompletedCount.current = completedCount;
  }, [isLoading, unknownCount, completedCount, allComplete]);

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
  const progressLabel =
    unknownCount > 0
      ? `${completedCount} of ${total} complete, ${unknownCount} not checked`
      : `${completedCount} of ${total} complete`;

  return (
    <section
      aria-label="Finish setup checklist"
      className={cn("overflow-hidden rounded-xl border bg-card shadow-sm", className)}
    >
      <div className="border-b px-6 py-5">
        <div className="flex items-start gap-4">
          <div
            className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-muted shadow-sm"
            aria-hidden="true"
          >
            {allComplete ? (
              <PartyPopper className="size-5 text-success" />
            ) : (
              <Rocket className="size-5 text-muted-foreground" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-semibold">
              {allComplete ? "You're all set!" : "Finish setup"}
            </p>
            <p className="text-sm text-muted-foreground">
              {allComplete
                ? "Every step is checked off. Your workspace is ready to run."
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
            <span className="font-medium">{progressLabel}</span>
            <span className="text-muted-foreground">{percentage}%</span>
          </div>
          <Progress
            value={percentage}
            aria-label={`Setup progress: ${progressLabel}`}
          />
        </div>

        {isError && (
          <div
            role="alert"
            className="mt-4 flex flex-col gap-3 rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 sm:flex-row sm:items-center"
          >
            <TriangleAlert className="hidden size-4 shrink-0 text-warning sm:block" aria-hidden="true" />
            <div className="min-w-0 flex-1 text-sm">
              <p className="font-medium">
                {unknownCount === total
                  ? "We couldn't check your setup"
                  : unknownCount > 0
                    ? `We couldn't check ${unknownCount} of ${total} steps`
                    : "We couldn't refresh your setup progress"}
              </p>
              <p className="text-muted-foreground">
                {unknownCount === total
                  ? "Some of these may already be done. Each step still links to where it happens."
                  : unknownCount > 0
                    ? "Those steps are marked below and may already be done. Everything else is up to date."
                    : "Showing your last known progress."}
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={retry}
              disabled={isRetrying}
              className="self-start sm:self-auto"
            >
              <RefreshCw
                className={cn("mr-2 size-3.5", isRetrying && "animate-spin")}
                aria-hidden="true"
              />
              {isRetrying ? "Checking…" : "Retry check"}
            </Button>
          </div>
        )}
      </div>

      <ul className="divide-y divide-border px-2 py-1">
        {steps.map((step) => (
          <li key={step.id}>
            <Link
              href={step.href}
              className="group flex items-center gap-3 rounded-lg px-4 py-3 transition-colors hover:bg-muted/50"
            >
              {step.state === "done" ? (
                <CheckCircle2
                  className="size-5 shrink-0 text-success"
                  aria-hidden="true"
                />
              ) : step.state === "unknown" ? (
                <CircleHelp className="size-5 shrink-0 text-warning" aria-hidden="true" />
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
                  <span className="sr-only">
                    {step.state === "done"
                      ? " (complete)"
                      : step.state === "unknown"
                        ? " (couldn't check)"
                        : " (todo)"}
                  </span>
                </span>
                {step.state === "unknown" && (
                  <span className="block text-xs font-medium text-warning" aria-hidden="true">
                    Couldn&apos;t check
                  </span>
                )}
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
