"use client";

import { AlarmClock, Check, Loader2, X } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { formatRelative, formatTime } from "@/lib/utils/date";
import type { PendingAction, PendingActionStatus } from "@/types/pending-action";

// Badge anatomy per the anti-tint rule: neutral surface + exactly one semantic
// marker (the dot). Color never carries meaning alone; the badge text is always
// the accessible cue, the dot is reinforcement.
const STATUS_DOT: Record<PendingActionStatus, string> = {
  pending: "bg-warning",
  approved: "bg-success",
  rejected: "bg-destructive",
  expired: "bg-muted-foreground",
  executed: "bg-info",
  failed: "bg-destructive",
};

const STATUS_LABEL: Record<PendingActionStatus, string> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
  expired: "Expired",
  executed: "Executed",
  failed: "Failed",
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

const SOURCE_LABELS: Record<string, string> = {
  crm_assistant: "the CRM assistant",
  text_conversation: "the SMS assistant",
  voice_call: "a voice call",
  automation: "an automation",
  deal_coach: "the deal coach",
  outbound_auto_draft: "autopilot outbound",
  reply_handler: "reply handling",
};

// Item labels that answer "to whom", rendered in the first column. Everything
// else (From, Appointment, Tag, ...) is supporting detail in the middle column.
const TO_COLUMN_LABELS = new Set(["Contact", "Recipient", "Email", "Audience"]);

interface PayloadDetailItem {
  label: string;
  value: string;
}

interface PendingActionPayloadSummary {
  items: PayloadDetailItem[];
  messageLabel?: string;
  message?: string;
}

interface SnoozeOption {
  key: string;
  label: string;
  until: Date;
}

function StatusBadge({ status }: { status: PendingActionStatus }) {
  return (
    <Badge variant="outline" className="gap-1.5 text-xs">
      <span aria-hidden="true" className={cn("size-2 rounded-full", STATUS_DOT[status])} />
      {STATUS_LABEL[status]}
    </Badge>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 space-y-1">
      <dt className="text-xs font-medium text-muted-foreground">{label}</dt>
      <dd className="break-words text-sm leading-relaxed whitespace-pre-wrap">{value}</dd>
    </div>
  );
}

interface PendingActionCardProps {
  action: PendingAction;
  onApprove: () => void;
  onReject: () => void;
  isApproving: boolean;
  isRejecting: boolean;
  /** Status badges are redundant on a status tab; show them on the All tab. */
  showStatus?: boolean;
  selected?: boolean;
  onSelectedChange?: (selected: boolean) => void;
  snooze?: {
    snoozedUntil: number | null;
    onSnooze: (until: Date) => void;
    onUndoSnooze: () => void;
  };
}

export function PendingActionCard({
  action,
  onApprove,
  onReject,
  isApproving,
  isRejecting,
  showStatus = false,
  selected,
  onSelectedChange,
  snooze,
}: PendingActionCardProps) {
  const isPending = action.status === "pending";
  const baseType = getBaseActionType(action.action_type);
  const payloadSummary = getPendingActionPayloadSummary(action);
  const why = getWhy(action);
  const failureReason =
    action.status === "failed" ? getFailureReason(action.execution_result) : undefined;
  const isSelected = selected === true;

  const [snoozeOpen, setSnoozeOpen] = useState(false);
  const [snoozeOptions, setSnoozeOptions] = useState<SnoozeOption[]>([]);

  const handleSnoozeOpenChange = (open: boolean) => {
    setSnoozeOpen(open);
    if (open) setSnoozeOptions(getSnoozeOptions(action.expires_at));
  };

  const toItems = payloadSummary
    ? payloadSummary.items.filter((item) => TO_COLUMN_LABELS.has(item.label))
    : [];
  const detailItems = payloadSummary
    ? payloadSummary.items.filter((item) => !TO_COLUMN_LABELS.has(item.label))
    : [];
  const hasMessage = Boolean(payloadSummary?.message);
  const hasDetails = detailItems.length > 0 || hasMessage;
  const showColumns = toItems.length > 0 || hasDetails || Boolean(why);

  const urgency = action.urgency.toLowerCase();
  const showUrgency = isPending && (urgency === "high" || urgency === "medium");

  return (
    <Card className={cn("py-0", isSelected && "border-primary/50")}>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
          <div className="flex min-w-0 items-start gap-3">
            {onSelectedChange && isPending ? (
              <Checkbox
                checked={isSelected}
                onCheckedChange={(checked) => onSelectedChange(checked === true)}
                aria-label={`Select action: ${action.description}`}
                className="mt-0.5"
              />
            ) : null}
            <div className="min-w-0 space-y-1.5">
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge variant="outline" className="text-xs">
                  {getTypeLabel(action.action_type)}
                </Badge>
                {showUrgency ? (
                  <Badge variant="outline" className="gap-1.5 text-xs">
                    {urgency === "high" ? (
                      <span aria-hidden="true" className="size-2 rounded-full bg-destructive" />
                    ) : null}
                    {urgency === "high" ? "High urgency" : "Medium urgency"}
                  </Badge>
                ) : null}
                {showStatus ? <StatusBadge status={action.status} /> : null}
              </div>
              <h2 className="break-words text-sm font-semibold leading-snug">
                {action.description}
              </h2>
            </div>
          </div>

          {isPending ? (
            <div className="ml-auto flex shrink-0 items-center gap-1.5">
              <Button
                size="sm"
                onClick={onApprove}
                disabled={isApproving || isRejecting}
                aria-label={`Approve: ${action.description}`}
              >
                {isApproving ? (
                  <Loader2 className="animate-spin" aria-hidden="true" />
                ) : (
                  <Check aria-hidden="true" />
                )}
                Approve
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={onReject}
                disabled={isApproving || isRejecting}
                aria-label={`Reject: ${action.description}`}
              >
                {isRejecting ? (
                  <Loader2 className="animate-spin" aria-hidden="true" />
                ) : (
                  <X aria-hidden="true" />
                )}
                Reject
              </Button>
              {snooze && snooze.snoozedUntil === null ? (
                <Popover open={snoozeOpen} onOpenChange={handleSnoozeOpenChange}>
                  <PopoverTrigger asChild>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={isApproving || isRejecting}
                      aria-label={`Snooze: ${action.description}`}
                    >
                      <AlarmClock aria-hidden="true" />
                      Snooze
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent align="end" className="w-60 p-2" aria-label="Snooze options">
                    <p className="px-2 pb-1.5 text-xs font-medium text-muted-foreground">
                      Snooze until
                    </p>
                    {snoozeOptions.length > 0 ? (
                      snoozeOptions.map((option) => (
                        <Button
                          key={option.key}
                          variant="ghost"
                          size="sm"
                          className="w-full justify-start font-normal"
                          onClick={() => {
                            setSnoozeOpen(false);
                            snooze.onSnooze(option.until);
                          }}
                        >
                          {option.label}
                          <span className="ml-auto text-xs text-muted-foreground">
                            {formatTime(option.until)}
                          </span>
                        </Button>
                      ))
                    ) : (
                      <p className="px-2 text-xs text-muted-foreground">
                        Expiring too soon to snooze.
                      </p>
                    )}
                  </PopoverContent>
                </Popover>
              ) : null}
            </div>
          ) : null}
        </div>

        {showColumns ? (
          <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2 xl:grid-cols-3">
            {toItems.length > 0 ? (
              <dl className="min-w-0 space-y-3">
                {toItems.map((item) => (
                  <Fact key={`${item.label}-${item.value}`} label={item.label} value={item.value} />
                ))}
              </dl>
            ) : null}

            {hasDetails ? (
              <dl className="min-w-0 space-y-3">
                {payloadSummary?.message ? (
                  <Fact
                    label={payloadSummary.messageLabel ?? "Message"}
                    value={payloadSummary.message}
                  />
                ) : null}
                {detailItems.map((item) => (
                  <Fact key={`${item.label}-${item.value}`} label={item.label} value={item.value} />
                ))}
              </dl>
            ) : null}

            {why ? (
              <dl className="min-w-0 space-y-3">
                <Fact label="Why" value={why} />
              </dl>
            ) : null}
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
          <span>Created {formatRelative(action.created_at)}</span>
          {isPending && action.expires_at ? (
            <span>
              Auto-rejects {formatRelative(action.expires_at)} ·{" "}
              {ACTION_TYPE_INACTION_VERB[baseType] ?? "won't run unless you approve"}
            </span>
          ) : null}
          {isPending && snooze?.snoozedUntil ? (
            <>
              <span>Snoozed until {formatTime(snooze.snoozedUntil)}</span>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-xs"
                onClick={snooze.onUndoSnooze}
                aria-label={`End snooze: ${action.description}`}
              >
                Undo snooze
              </Button>
            </>
          ) : null}
          {action.status === "approved" ? (
            <span>Approved {formatRelative(action.reviewed_at ?? action.updated_at)}</span>
          ) : null}
          {action.status === "rejected" ? (
            <span>
              Rejected {formatRelative(action.reviewed_at ?? action.updated_at)}
              {action.rejection_reason ? ` · Reason: ${action.rejection_reason}` : ""}
            </span>
          ) : null}
          {action.status === "expired" ? (
            <span>Expired {formatRelative(action.expires_at ?? action.updated_at)}</span>
          ) : null}
          {action.status === "executed" ? (
            <span>Executed {formatRelative(action.executed_at ?? action.updated_at)}</span>
          ) : null}
          {failureReason ? (
            <span>
              Execution failed {formatRelative(action.updated_at)}: {failureReason}
            </span>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function getBaseActionType(actionType: string): string {
  return actionType.includes(".") ? actionType.slice(actionType.lastIndexOf(".") + 1) : actionType;
}

function getTypeLabel(actionType: string): string {
  const baseType = getBaseActionType(actionType);
  const known = ACTION_TYPE_LABELS[baseType];
  if (known) return known;
  const humanized = baseType.replace(/[_-]+/g, " ");
  return humanized.charAt(0).toUpperCase() + humanized.slice(1);
}

function humanizeSource(source: string): string {
  return source.replace(/[_-]+/g, " ");
}

/**
 * Why this action is waiting for a human: an explicit rationale when the
 * producer recorded one, the deal coach's top risk, otherwise the requesting
 * source and risk level from the approval-gate context.
 */
function getWhy(action: PendingAction): string | undefined {
  const payload = action.action_payload;
  const context = action.context;

  const direct =
    getFirstString(payload, ["rationale", "reason", "why", "justification"]) ??
    getNestedString(
      payload,
      ["next_best_action", "recommended_campaign", "recommendation"],
      ["rationale", "reason", "why", "justification"],
    );
  if (direct) return direct;

  const topRisk = getFirstString(context, ["top_risk"]);
  if (topRisk) return topRisk;

  const source = getFirstString(context, ["source"]);
  const risk = getFirstString(context, ["risk_level"]);
  if (!source && !risk) return undefined;

  const by = source
    ? `Requested by ${SOURCE_LABELS[source] ?? humanizeSource(source)}`
    : "Queued for review";
  return risk ? `${by} (risk: ${risk})` : by;
}

function getSnoozeOptions(expiresAt: string | null): SnoozeOption[] {
  const now = new Date();
  const expires = expiresAt ? new Date(expiresAt) : null;
  // An unparseable expiry simply means "no cap".
  const validExpires = expires && !Number.isNaN(expires.getTime()) ? expires : null;

  const endOfDay = new Date(now);
  endOfDay.setHours(17, 0, 0, 0);
  const tomorrowMorning = new Date(now);
  tomorrowMorning.setDate(tomorrowMorning.getDate() + 1);
  tomorrowMorning.setHours(9, 0, 0, 0);

  const candidates: SnoozeOption[] = [
    { key: "1h", label: "In 1 hour", until: new Date(now.getTime() + 60 * 60 * 1000) },
    { key: "3h", label: "In 3 hours", until: new Date(now.getTime() + 3 * 60 * 60 * 1000) },
    { key: "eod", label: "Later today", until: endOfDay },
    { key: "tomorrow", label: "Tomorrow morning", until: tomorrowMorning },
  ];

  // Never snooze past the auto-reject deadline: the action must come back to
  // the operator before it expires, not stay hidden until it is already dead.
  const capped = candidates.map((option) =>
    validExpires && option.until > validExpires
      ? { ...option, until: new Date(validExpires.getTime()) }
      : option,
  );

  const seen = new Set<number>();
  return capped.filter((option) => {
    const time = option.until.getTime();
    if (time <= now.getTime() || seen.has(time)) return false;
    seen.add(time);
    return true;
  });
}

function getPendingActionPayloadSummary(action: PendingAction): PendingActionPayloadSummary | null {
  const payload = action.action_payload;

  switch (getBaseActionType(action.action_type)) {
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
    default: {
      // Generic fallback so campaign launches, deal-coach drafts, and assistant
      // tools still show who this touches and what will go out.
      const previews = getMessagePreviews(payload);
      return compactSummary({
        items: [
          detailItem("Contact", getContactName(payload)),
          detailItem("Recipient", getRecipient(payload)),
          detailItem(
            "Audience",
            getNestedString(
              payload,
              ["segment", "audience", "target_segment"],
              ["name", "label", "title"],
            ),
          ),
          detailItem("Offer", getNestedString(payload, ["offer"], ["name", "title"])),
          detailItem(
            "Responder",
            getNestedString(
              payload,
              ["responder_agent", "responder"],
              ["name", "label", "display_name"],
            ),
          ),
          detailItem("Channel", getFirstString(payload, ["channel"])),
          detailItem("Launch status", humanizeStatus(getFirstString(payload, ["launch_status"]))),
        ],
        messageLabel: previews ? "Messages" : "Message",
        message:
          getFirstString(payload, ["text", "body", "message", "message_body", "content"]) ??
          previews,
      });
    }
  }
}

function humanizeStatus(status: string | undefined): string | undefined {
  if (!status) return undefined;
  const humanized = status.replace(/[_-]+/g, " ");
  return humanized.charAt(0).toUpperCase() + humanized.slice(1);
}

function getMessagePreviews(payload: Record<string, unknown>): string | undefined {
  const previews = payload.message_previews;
  if (!Array.isArray(previews)) return undefined;
  const texts = previews.filter(
    (entry): entry is string => typeof entry === "string" && entry.trim().length > 0,
  );
  return texts.length > 0 ? texts.join("\n\n") : undefined;
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
