"use client";

import { Check, X, Clock, Loader2 } from "lucide-react";

import {
  isOutboundWorkflowAction,
  OutboundWorkflowCard,
} from "@/components/assistant/outbound-workflow-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { formatRelative } from "@/lib/utils/date";
import type { PendingAction } from "@/types/pending-action";

const URGENCY_STYLES: Record<string, string> = {
  high: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  medium: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  low: "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200",
};

const ACTION_TYPE_STYLES: Record<string, string> = {
  book_appointment: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  send_sms: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  enroll_campaign: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
  apply_tag: "bg-cyan-100 text-cyan-800 dark:bg-cyan-900 dark:text-cyan-200",
};

const ACTION_TYPE_LABELS: Record<string, string> = {
  book_appointment: "Book Appointment",
  send_sms: "Send SMS",
  enroll_campaign: "Enroll Campaign",
  apply_tag: "Apply Tag",
};

// Verb describing what *won't* happen if the operator ignores the action until
// it expires. At expiry the worker auto-rejects (never auto-executes), so the
// outcome is always "this won't happen unless you approve".
const ACTION_TYPE_INACTION_VERB: Record<string, string> = {
  book_appointment: "won't book unless you approve",
  send_sms: "won't send unless you approve",
  enroll_campaign: "won't enroll unless you approve",
  apply_tag: "won't apply unless you approve",
};

interface PayloadDetailItem {
  label: string;
  value: string;
}

interface PendingActionPayloadSummary {
  items: PayloadDetailItem[];
  messageLabel?: string;
  message?: string;
}

function getStatusBadge(status: string) {
  switch (status) {
    case "pending":
      return <Badge variant="outline">Pending</Badge>;
    case "approved":
      return (
        <Badge variant="default" className="bg-green-600">
          Approved
        </Badge>
      );
    case "rejected":
      return <Badge variant="destructive">Rejected</Badge>;
    case "expired":
      return <Badge variant="secondary">Expired</Badge>;
    case "executed":
      return (
        <Badge variant="default" className="bg-blue-600">
          Executed
        </Badge>
      );
    case "failed":
      return <Badge variant="destructive">Failed</Badge>;
    default:
      return <Badge variant="secondary">{status}</Badge>;
  }
}

interface PendingActionCardProps {
  action: PendingAction;
  onApprove: () => void;
  onReject: () => void;
  isApproving: boolean;
  isRejecting: boolean;
}

export function PendingActionCard({
  action,
  onApprove,
  onReject,
  isApproving,
  isRejecting,
}: PendingActionCardProps) {
  const isPending = action.status === "pending";
  const payloadSummary = getPendingActionPayloadSummary(action);
  const failureReason =
    action.status === "failed" ? getFailureReason(action.execution_result) : undefined;

  if (isOutboundWorkflowAction(action)) {
    return (
      <OutboundWorkflowCard
        action={action}
        onApprove={onApprove}
        onReject={onReject}
        isApproving={isApproving}
        isRejecting={isRejecting}
      />
    );
  }

  return (
    <Card>
      <CardContent className="flex items-start gap-4 p-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-muted">
          <Clock className="h-5 w-5 text-muted-foreground" />
        </div>

        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h3 className="font-medium leading-tight">{action.description}</h3>
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              <Badge
                className={cn(
                  "text-xs",
                  ACTION_TYPE_STYLES[action.action_type] || "bg-gray-100 text-gray-800",
                )}
              >
                {ACTION_TYPE_LABELS[action.action_type] || action.action_type}
              </Badge>
              <Badge
                className={cn("text-xs", URGENCY_STYLES[action.urgency] || URGENCY_STYLES.low)}
              >
                {action.urgency}
              </Badge>
              {getStatusBadge(action.status)}
            </div>
          </div>

          {payloadSummary ? <PayloadSummary summary={payloadSummary} /> : null}

          {failureReason ? (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              <span className="font-medium">Failed:</span> {failureReason}
            </div>
          ) : null}

          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span>Created {formatRelative(action.created_at)}</span>
            {action.expires_at &&
              (isPending ? (
                <span className="text-amber-600 dark:text-amber-400">
                  Auto-rejected {formatRelative(action.expires_at)} —{" "}
                  {ACTION_TYPE_INACTION_VERB[action.action_type] ?? "won't run unless you approve"}
                </span>
              ) : (
                <span>Expires {formatRelative(action.expires_at)}</span>
              ))}
            {action.rejection_reason && (
              <span className="italic">Reason: {action.rejection_reason}</span>
            )}
          </div>
        </div>

        {isPending && (
          <div className="flex shrink-0 items-center gap-1">
            <Button
              size="sm"
              onClick={onApprove}
              disabled={isApproving || isRejecting}
              className="bg-green-600 hover:bg-green-700"
            >
              {isApproving ? (
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Check className="mr-1 h-3.5 w-3.5" />
              )}
              Approve
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={onReject}
              disabled={isApproving || isRejecting}
              className="text-destructive"
            >
              {isRejecting ? (
                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
              ) : (
                <X className="mr-1 h-3.5 w-3.5" />
              )}
              Reject
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PayloadSummary({ summary }: { summary: PendingActionPayloadSummary }) {
  return (
    <div className="space-y-3 rounded-lg border bg-muted/20 p-3">
      {summary.items.length > 0 ? (
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {summary.items.map((item) => (
            <div key={`${item.label}-${item.value}`} className="min-w-0">
              <dt className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
                {item.label}
              </dt>
              <dd className="mt-0.5 break-words text-sm font-medium text-foreground">
                {item.value}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}

      {summary.message ? (
        <div className="rounded-md border bg-background/70 p-3">
          <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            {summary.messageLabel ?? "Message"}
          </p>
          <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">
            {summary.message}
          </p>
        </div>
      ) : null}
    </div>
  );
}

function getPendingActionPayloadSummary(action: PendingAction): PendingActionPayloadSummary | null {
  const payload = action.action_payload;

  switch (action.action_type) {
    case "send_sms":
      return compactSummary({
        items: [
          detailItem("Contact", getContactName(payload)),
          detailItem("Recipient", getRecipient(payload)),
          detailItem("From", getFirstString(payload, ["from_number", "from_phone_number"])),
        ],
        messageLabel: "Message to send",
        message: getFirstString(payload, ["text", "body", "message", "message_body", "content"]),
      });
    case "book_appointment":
      return compactSummary({
        items: [
          detailItem("Contact", getContactName(payload)),
          detailItem("Recipient", getRecipient(payload)),
          detailItem("Appointment", getAppointmentTime(payload)),
          detailItem(
            "Email",
            getFirstString(payload, ["email", "contact_email", "recipient_email"]),
          ),
          detailItem("Duration", getDuration(payload)),
        ],
        messageLabel: "Appointment note",
        message: getFirstString(payload, ["notes", "note", "message", "message_body", "body"]),
      });
    case "apply_tag":
      return compactSummary({
        items: [
          detailItem("Contact", getContactName(payload)),
          detailItem("Recipient", getRecipient(payload)),
          detailItem("Tag", getFirstString(payload, ["tag", "tag_name", "label", "name"])),
        ],
      });
    default:
      return null;
  }
}

function getFailureReason(executionResult: Record<string, unknown> | null): string | undefined {
  if (!executionResult) return "No execution reason was recorded.";

  return (
    getFirstString(executionResult, ["error", "reason", "message", "detail", "failure_reason"]) ??
    "No execution reason was recorded."
  );
}

function compactSummary(summary: PendingActionPayloadSummary): PendingActionPayloadSummary | null {
  const items = summary.items.filter((item) => item.value.trim().length > 0);
  const message = summary.message?.trim();

  if (items.length === 0 && !message) return null;

  return {
    ...summary,
    items,
    message,
  };
}

function detailItem(label: string, value?: string): PayloadDetailItem {
  return { label, value: value ?? "" };
}

function getContactName(payload: Record<string, unknown>): string | undefined {
  return (
    getFirstString(payload, [
      "contact_name",
      "recipient_name",
      "customer_name",
      "lead_name",
      "full_name",
      "display_name",
      "name",
    ]) ??
    getNestedString(
      payload,
      ["contact", "recipient", "lead", "customer"],
      ["name", "full_name", "display_name"],
    )
  );
}

function getRecipient(payload: Record<string, unknown>): string | undefined {
  return (
    getFirstString(payload, [
      "to_number",
      "phone_number",
      "recipient_phone_number",
      "recipient_phone",
      "contact_phone_number",
      "contact_phone",
      "to_phone_number",
      "phone",
      "to",
    ]) ??
    getNestedString(
      payload,
      ["recipient", "contact", "lead", "customer"],
      ["phone_number", "phone", "mobile"],
    )
  );
}

function getAppointmentTime(payload: Record<string, unknown>): string | undefined {
  const date = getFirstString(payload, ["date", "appointment_date", "start_date"]);
  const time = getFirstString(payload, ["time", "appointment_time", "start_time"]);
  const timezone = getFirstString(payload, ["timezone", "time_zone"]);
  const startsAt = getFirstString(payload, ["starts_at", "start_time_iso", "scheduled_at"]);

  if (date || time) return [date, time, timezone].filter(Boolean).join(" ");
  return startsAt;
}

function getDuration(payload: Record<string, unknown>): string | undefined {
  const duration = getFirstString(payload, ["duration", "duration_label"]);
  if (duration) return duration;

  const minutes = getFirstNumber(payload, ["duration_minutes", "duration_in_minutes"]);
  return typeof minutes === "number" ? `${minutes} min` : undefined;
}

function getFirstString(payload: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "string" && value.trim().length > 0) return value;
    if (typeof value === "number" && Number.isFinite(value)) return String(value);
  }
  return undefined;
}

function getFirstNumber(payload: Record<string, unknown>, keys: string[]): number | undefined {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && value.trim().length > 0) {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) return parsed;
    }
  }
  return undefined;
}

function getNestedString(
  payload: Record<string, unknown>,
  recordKeys: string[],
  valueKeys: string[],
): string | undefined {
  for (const recordKey of recordKeys) {
    const value = payload[recordKey];
    if (!isRecord(value)) continue;

    const nested = getFirstString(value, valueKeys);
    if (nested) return nested;
  }
  return undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
