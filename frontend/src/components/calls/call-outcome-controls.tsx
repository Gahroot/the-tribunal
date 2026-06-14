"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { callsApi, type CallOutcome } from "@/lib/api/calls";
import { queryKeys } from "@/lib/query-keys";
import { cn } from "@/lib/utils";
import { getApiErrorMessage } from "@/lib/utils/errors";

const OUTCOME_OPTIONS = [
  { value: "appointment_booked", label: "Appointment booked" },
  { value: "lead_qualified", label: "Lead qualified" },
  { value: "completed", label: "Completed" },
  { value: "voicemail", label: "Voicemail" },
  { value: "no_answer", label: "No answer" },
  { value: "busy", label: "Busy" },
  { value: "rejected", label: "Rejected" },
  { value: "failed", label: "Failed" },
] as const;

const outcomeStyles: Record<string, string> = {
  appointment_booked: "bg-success/10 text-success border-success/20",
  lead_qualified: "bg-info/10 text-info border-info/20",
  completed: "bg-primary/10 text-primary border-primary/20",
  voicemail: "bg-warning/10 text-warning border-warning/20",
  no_answer: "bg-muted text-muted-foreground",
  busy: "bg-muted text-muted-foreground",
  rejected: "bg-destructive/10 text-destructive border-destructive/20",
  failed: "bg-destructive/10 text-destructive border-destructive/20",
};

function formatOutcomeLabel(outcomeType: string | null | undefined): string {
  if (!outcomeType) return "Unclassified";
  return OUTCOME_OPTIONS.find((option) => option.value === outcomeType)?.label
    ?? outcomeType.replaceAll("_", " ");
}

function getOutcomeBadgeClass(outcomeType: string | null | undefined): string {
  if (!outcomeType) return "bg-muted text-muted-foreground";
  return outcomeStyles[outcomeType] ?? "bg-muted text-muted-foreground";
}

interface CallOutcomeControlsProps {
  workspaceId: string;
  messageId: string;
  variant?: "row" | "detail";
  className?: string;
}

export function CallOutcomeControls({
  workspaceId,
  messageId,
  variant = "row",
  className,
}: CallOutcomeControlsProps) {
  const queryClient = useQueryClient();
  const [submittedThumb, setSubmittedThumb] = useState<"up" | "down" | null>(null);
  const outcomeQueryKey = queryKeys.calls.outcome(workspaceId, messageId);
  const feedbackQueryKey = queryKeys.calls.feedback(workspaceId, messageId);

  const { data: outcome, isPending: isOutcomePending } = useQuery({
    queryKey: outcomeQueryKey,
    queryFn: () => callsApi.getOutcome(workspaceId, messageId),
    enabled: !!workspaceId && !!messageId,
    staleTime: 30_000,
  });

  const updateOutcomeMutation = useMutation({
    mutationFn: (outcomeType: string) =>
      callsApi.updateOutcome(workspaceId, messageId, {
        outcome_type: outcomeType,
        classified_by: "user",
        classification_confidence: 1,
        signals: {
          ...(outcome?.signals ?? {}),
          user_corrected: true,
          correction_source: "calls_ui",
        },
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData<CallOutcome | null>(outcomeQueryKey, (current) => ({
        ...current,
        ...updated,
        booking_outcome: current?.booking_outcome,
        call_direction: current?.call_direction,
        call_duration_seconds: current?.call_duration_seconds,
        prompt_is_baseline: current?.prompt_is_baseline,
        prompt_version_number: current?.prompt_version_number,
      }));
      toast.success(`Reclassified as ${formatOutcomeLabel(updated.outcome_type)}`);
      void queryClient.invalidateQueries({ queryKey: outcomeQueryKey });
    },
    onError: (error: unknown) =>
      toast.error(getApiErrorMessage(error, "Couldn't reclassify this call")),
  });

  const feedbackMutation = useMutation({
    mutationFn: (thumbs: "up" | "down") =>
      callsApi.submitFeedback(workspaceId, messageId, {
        source: "user",
        thumbs,
        feedback_signals: {
          outcome_type: outcome?.outcome_type ?? null,
          ui_surface: variant,
        },
      }),
    onSuccess: (feedback) => {
      const thumbs = feedback.thumbs === "down" ? "down" : "up";
      setSubmittedThumb(thumbs);
      toast.success(thumbs === "up" ? "Marked as helpful" : "Marked for coaching");
      void queryClient.invalidateQueries({ queryKey: feedbackQueryKey });
    },
    onError: (error: unknown) =>
      toast.error(getApiErrorMessage(error, "Couldn't submit feedback for this call")),
  });

  const selectedOutcome = outcome?.outcome_type;
  const hasOutcome = !!selectedOutcome;
  const isBusy = isOutcomePending || updateOutcomeMutation.isPending;
  const isDetail = variant === "detail";

  const outcomeBadge = (
    <Badge
      variant="outline"
      className={cn("capitalize", getOutcomeBadgeClass(selectedOutcome))}
      data-testid="call-outcome-badge"
    >
      {isOutcomePending ? (
        <>
          <Loader2 className="size-3 animate-spin" />
          Loading outcome
        </>
      ) : (
        <>Outcome: {formatOutcomeLabel(selectedOutcome)}</>
      )}
    </Badge>
  );

  const reclassifySelect = (
    <Select
      value={selectedOutcome ?? ""}
      onValueChange={(value) => updateOutcomeMutation.mutate(value)}
      disabled={isBusy || !hasOutcome}
    >
      <SelectTrigger
        className={cn(isDetail ? "w-full" : "h-7 w-[155px] text-xs")}
        aria-label="Reclassify call outcome"
        data-testid="call-outcome-reclassify"
      >
        <SelectValue placeholder={hasOutcome ? "Reclassify" : "No outcome yet"} />
      </SelectTrigger>
      <SelectContent>
        {OUTCOME_OPTIONS.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  const feedbackButtons = (
    <div className="flex items-center gap-1" data-testid="call-feedback-controls">
      <Button
        type="button"
        variant={submittedThumb === "up" ? "secondary" : "outline"}
        size={isDetail ? "sm" : "icon-sm"}
        className={cn(!isDetail && "size-7")}
        onClick={() => feedbackMutation.mutate("up")}
        disabled={feedbackMutation.isPending || !workspaceId || !messageId}
        aria-label="Submit thumbs-up call feedback"
      >
        {feedbackMutation.isPending ? <Loader2 className="size-3 animate-spin" /> : <ThumbsUp className="size-3" />}
        {isDetail ? "Helpful" : null}
      </Button>
      <Button
        type="button"
        variant={submittedThumb === "down" ? "secondary" : "outline"}
        size={isDetail ? "sm" : "icon-sm"}
        className={cn(!isDetail && "size-7")}
        onClick={() => feedbackMutation.mutate("down")}
        disabled={feedbackMutation.isPending || !workspaceId || !messageId}
        aria-label="Submit thumbs-down call feedback"
      >
        {submittedThumb === "down" && !feedbackMutation.isPending ? (
          <Check className="size-3" />
        ) : (
          <ThumbsDown className="size-3" />
        )}
        {isDetail ? "Needs coaching" : null}
      </Button>
    </div>
  );

  if (!isDetail) {
    return (
      <div className={cn("mt-2 flex flex-wrap items-center gap-1.5", className)}>
        {outcomeBadge}
        {reclassifySelect}
        {feedbackButtons}
      </div>
    );
  }

  return (
    <section className={cn("rounded-md border bg-muted/20 p-3 space-y-3", className)}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="space-y-1">
          <h4 className="font-medium">Outcome & AI coaching</h4>
          <p className="text-xs text-muted-foreground">
            Correct the AI result and rate whether this call was handled well.
          </p>
        </div>
        {outcomeBadge}
      </div>
      <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground">Reclassify outcome</p>
          {reclassifySelect}
        </div>
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-muted-foreground">Feedback</p>
          {feedbackButtons}
        </div>
      </div>
      {outcome?.classified_by ? (
        <p className="text-xs text-muted-foreground">
          Classified by {outcome.classified_by.replaceAll("_", " ")}
          {typeof outcome.classification_confidence === "number"
            ? ` · ${Math.round(outcome.classification_confidence * 100)}% confidence`
            : ""}
        </p>
      ) : null}
    </section>
  );
}
