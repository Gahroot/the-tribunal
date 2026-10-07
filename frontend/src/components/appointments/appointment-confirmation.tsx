"use client";

import {
  CalendarCheck2,
  CheckCircle2,
  Clock,
  ExternalLink,
  Loader2,
  Plus,
  UserX,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { toast } from "sonner";

import {
  ReminderBadges,
  SendReminderButton,
  SyncButton,
} from "@/components/appointments/appointment-actions";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useAgent } from "@/hooks/useAgents";
import { useCancelAppointment } from "@/hooks/useAppointments";
import type { CancelAppointmentResult } from "@/lib/api/appointments";
import {
  getContactName,
  getInitials,
} from "@/lib/calendar/calendar-derivations";
import { cn } from "@/lib/utils";
import { formatDate } from "@/lib/utils/date";
import { getApiErrorCode, getApiErrorMessage } from "@/lib/utils/errors";
import type { Appointment } from "@/types";

/**
 * Appointment confirmation flow rendered inside the calendar detail dialog.
 *
 * States (mirroring the Cal.com webhook-driven `status` field):
 * - scheduled: full meeting details plus reschedule/cancel actions in one rail;
 * - inline cancel confirmation with an optional reason, focus moved into the
 *   confirmation block and returned to the cancel trigger on dismissal;
 * - cancelled: state header plus a Reason row (`cancellation_reason`,
 *   "Unspecified" when absent) and a rebook action.
 *
 * Cancelling a Cal.com-backed appointment cancels the Cal.com booking first;
 * the CRM only shows "cancelled" once Cal.com confirms. If Cal.com fails, the
 * operator can retry or explicitly cancel in the CRM only, which leaves a
 * visible "Cal.com booking still active" state with a retry action.
 */

type Phase = "view" | "confirm";

interface AppointmentConfirmationProps {
  appointment: Appointment;
  workspaceId: string;
  /** Re-fetch after sync/reminder/cancel so webhook-driven status stays visible. */
  onRefresh: () => void;
  /** Recovery path after cancellation: opens the new-appointment flow. */
  onRebook: () => void;
}

const STATUS_META: Record<
  Appointment["status"],
  { title: string; icon: LucideIcon; tone: string; srDescription: string }
> = {
  scheduled: {
    title: "This appointment is scheduled",
    icon: CalendarCheck2,
    tone: "text-success border",
    srDescription: "Scheduled appointment details.",
  },
  completed: {
    title: "This appointment is completed",
    icon: CheckCircle2,
    tone: "text-success border",
    srDescription: "Completed appointment details.",
  },
  cancelled: {
    title: "This appointment is cancelled",
    icon: XCircle,
    tone: "text-destructive border",
    srDescription: "Cancelled appointment details.",
  },
  no_show: {
    title: "This appointment was a no-show",
    icon: UserX,
    tone: "text-warning border",
    srDescription: "No-show appointment details.",
  },
};

function timeRangeLabel(startIso: string, durationMinutes: number): string {
  const start = new Date(startIso);
  const end = new Date(start.getTime() + durationMinutes * 60_000);
  return `${formatDate(start, { pattern: "h:mm a" })} – ${formatDate(end, {
    pattern: "h:mm a",
  })}`;
}

function timeZoneLabel(date: Date): string {
  return (
    new Intl.DateTimeFormat(undefined, { timeZoneName: "short" })
      .formatToParts(date)
      .find((part) => part.type === "timeZoneName")?.value ?? ""
  );
}

const ROW_LABEL_CLASS = "font-medium text-muted-foreground";

export function AppointmentConfirmation({
  appointment,
  workspaceId,
  onRefresh,
  onRebook,
}: AppointmentConfirmationProps) {
  const [phase, setPhase] = useState<Phase>("view");
  const [reason, setReason] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  // Set when Cal.com refused the cancel and a CRM-only cancel is possible.
  const [offerCrmOnly, setOfferCrmOnly] = useState(false);
  const [result, setResult] = useState<CancelAppointmentResult | null>(null);
  const [retryError, setRetryError] = useState<string | null>(null);

  const cancelMutation = useCancelAppointment(workspaceId);

  // Optional agent lookup: a blank workspace id keeps the query disabled when
  // the appointment has no agent.
  const agentId = appointment.agent_id;
  const { data: agent } = useAgent(agentId ? workspaceId : "", agentId ?? "");

  // After a successful cancel, the mutation response settles the UI into the
  // cancelled state immediately, even before the list refetch lands. Once the
  // webhook-driven server status arrives, it takes over.
  const latestCancel =
    result?.appointment.id === appointment.id ? result.appointment : undefined;
  const status: Appointment["status"] =
    appointment.status === "scheduled" && latestCancel?.status === "cancelled"
      ? "cancelled"
      : appointment.status;

  const baseId = useId();
  const reasonId = `${baseId}-reason`;
  const errorId = `${baseId}-cancel-error`;
  const confirmHeadingId = `${baseId}-cancel-heading`;

  const headingRef = useRef<HTMLHeadingElement>(null);
  const confirmHeadingRef = useRef<HTMLHeadingElement>(null);
  const cancelBtnRef = useRef<HTMLButtonElement>(null);
  const returnFocusRef = useRef(false);

  // Enter the confirmation block at its heading; on dismissal, hand focus back
  // to the cancel trigger that opened it.
  useEffect(() => {
    if (phase === "confirm") {
      confirmHeadingRef.current?.focus();
    } else if (returnFocusRef.current) {
      returnFocusRef.current = false;
      cancelBtnRef.current?.focus();
    }
  }, [phase]);

  // When status changes to cancelled (our cancel, or a Cal.com webhook while
  // the dialog is open), settle into the cancelled state and announce the new
  // heading by moving focus to it.
  const prevStatusRef = useRef(status);
  useEffect(() => {
    if (prevStatusRef.current === status) return;
    const becameCancelled = status === "cancelled";
    prevStatusRef.current = status;
    setPhase("view");
    if (becameCancelled) {
      headingRef.current?.focus();
    }
  }, [status]);

  const isPending = cancelMutation.isPending;

  const keepAppointment = () => {
    returnFocusRef.current = true;
    setFormError(null);
    setOfferCrmOnly(false);
    setPhase("view");
  };

  // Escape inside the confirmation controls backs out instead of letting the
  // dialog close underneath the user mid-reason.
  const handleConfirmKeyDown = (event: ReactKeyboardEvent) => {
    if (event.key === "Escape" && !isPending) {
      event.stopPropagation();
      keepAppointment();
    }
  };

  const cancelAppointment = (crmOnly = false) => {
    if (!workspaceId) {
      setFormError("No workspace selected. Reload the page and try again.");
      return;
    }
    setFormError(null);
    const trimmed = reason.trim();
    cancelMutation.mutate(
      {
        id: appointment.id,
        data: {
          ...(trimmed ? { reason: trimmed } : {}),
          ...(crmOnly ? { crm_only: true } : {}),
        },
      },
      {
        onSuccess: (data) => {
          setResult(data);
          setOfferCrmOnly(false);
          setPhase("view");
          setReason("");
          onRefresh();
          if (data.provider_result === "skipped") {
            toast.warning("Cancelled in the CRM only. Cal.com booking still active.");
          } else {
            toast.success("Appointment cancelled");
          }
        },
        onError: (error) => {
          setOfferCrmOnly(getApiErrorCode(error) === "calendar_cancel_failed");
          setFormError(
            getApiErrorMessage(error, "Could not cancel the appointment."),
          );
        },
      },
    );
  };

  // Recovery for a CRM-only cancel: retry cancelling the Cal.com booking.
  const retryProviderCancel = () => {
    setRetryError(null);
    cancelMutation.mutate(
      { id: appointment.id, data: {} },
      {
        onSuccess: (data) => {
          setResult(data);
          onRefresh();
          toast.success("Cal.com booking cancelled");
        },
        onError: (error) => {
          setRetryError(
            getApiErrorMessage(error, "Could not cancel the Cal.com booking."),
          );
        },
      },
    );
  };

  const meta = STATUS_META[status];
  const contact = appointment.contact;
  const bookingUid = appointment.calcom_booking_uid;
  const start = new Date(appointment.scheduled_at);
  const tzLabel = timeZoneLabel(start);
  const isScheduled = status === "scheduled";
  const showingConfirm = isScheduled && phase === "confirm";
  // Prefer the latest cancel response so the typed reason shows in the
  // cancelled state immediately, even before the list refetch lands.
  const current = latestCancel ?? appointment;
  const notes = appointment.notes?.trim();
  const cancellationReason = current.cancellation_reason?.trim();
  // Cancelled in the CRM only while the Cal.com booking is still live.
  const externalStillActive =
    status === "cancelled" &&
    Boolean(bookingUid) &&
    current.sync_status === "local_only";

  let descriptionText: string | null = null;
  if (isScheduled) {
    if (bookingUid && contact?.email) {
      descriptionText = `Calendar invite sent to ${contact.email}.`;
    } else if (bookingUid) {
      descriptionText = "Calendar invite sent to the contact.";
    } else {
      descriptionText = "Not synced to Cal.com yet. Sync to send the invite.";
    }
  }

  const contactSecondary = [contact?.email, contact?.phone_number]
    .filter(Boolean)
    .join(" · ");
  const depositAmount = `$${(appointment.deposit_amount_cents ?? 0) / 100}`;
  const depositLabel = {
    pending: appointment.deposit_amount_cents
      ? `Optional ${depositAmount} deposit pending`
      : "Optional card setup pending",
    paid: `Refundable ${depositAmount} received`,
    card_saved: "Card saved, no charge",
    refund_pending: "Refund in progress",
    refunded: "Refunded",
    none: "",
  }[appointment.deposit_status ?? "none"];

  return (
    <>
      <DialogHeader className="items-center text-center sm:items-center sm:text-center">
        <span
          aria-hidden="true"
          className={cn(
            "flex size-12 items-center justify-center rounded-full border",
            meta.tone,
          )}
        >
          <meta.icon className="size-6" />
        </span>
        <DialogTitle ref={headingRef} tabIndex={-1} className="leading-snug">
          {meta.title}
        </DialogTitle>
        {descriptionText ? (
          <DialogDescription>{descriptionText}</DialogDescription>
        ) : (
          <DialogDescription className="sr-only">
            {meta.srDescription}
          </DialogDescription>
        )}
      </DialogHeader>

      {/* Actions rail: reschedule and cancel live together in one place. */}
      {isScheduled && phase === "view" && (
        <div className="flex flex-wrap items-center justify-center gap-2">
          {bookingUid ? (
            <Button variant="outline" asChild>
              <a
                href={`https://cal.com/reschedule/${bookingUid}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                <Clock />
                Reschedule
                <span className="sr-only"> on Cal.com (opens in a new tab)</span>
              </a>
            </Button>
          ) : (
            <Button
              variant="outline"
              disabled
              title="Available after the appointment syncs to Cal.com"
            >
              <Clock />
              Reschedule
              <span className="sr-only"> (available after Cal.com sync)</span>
            </Button>
          )}
          <Button
            ref={cancelBtnRef}
            variant="outline"
            className="text-destructive hover:text-destructive"
            onClick={() => {
              setFormError(null);
              setPhase("confirm");
            }}
          >
            Cancel appointment
          </Button>
          {workspaceId && (
            <>
              <SyncButton
                appointment={appointment}
                workspaceId={workspaceId}
                onSynced={onRefresh}
              />
              <SendReminderButton
                appointment={appointment}
                workspaceId={workspaceId}
                onSent={onRefresh}
              />
            </>
          )}
        </div>
      )}

      {/* Inline cancel confirmation (Esc on its controls returns to the rail). */}
      {showingConfirm && (
        <div
          role="group"
          aria-labelledby={confirmHeadingId}
          className="space-y-3 rounded-lg border border-destructive/50 p-4"
          aria-busy={isPending}
        >
          <div className="space-y-1">
            <h3
              id={confirmHeadingId}
              ref={confirmHeadingRef}
              tabIndex={-1}
              className="text-sm font-semibold"
            >
              Cancel this appointment?
            </h3>
            <p className="text-sm text-muted-foreground">
              {bookingUid
                ? "This also cancels the Cal.com booking. Cal.com sends its own cancellation notice based on your event settings; the CRM sends no message."
                : "This appointment is not on Cal.com, so only the CRM is updated. The contact is not notified."}
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={reasonId}>Reason (optional)</Label>
            <Textarea
              id={reasonId}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="e.g. Client asked to move to next week"
              className="min-h-20"
              onKeyDown={handleConfirmKeyDown}
              aria-invalid={formError ? true : undefined}
              aria-describedby={formError ? errorId : undefined}
            />
          </div>
          {formError && (
            <p id={errorId} role="alert" className="text-sm text-destructive">
              {formError}
            </p>
          )}
          {offerCrmOnly && (
            <div className="flex justify-end">
              <Button
                variant="link"
                className="h-auto p-0 text-destructive"
                onClick={() => cancelAppointment(true)}
                onKeyDown={handleConfirmKeyDown}
                disabled={isPending}
              >
                Cancel in CRM only (Cal.com booking stays active)
              </Button>
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button
              variant="outline"
              onClick={keepAppointment}
              onKeyDown={handleConfirmKeyDown}
              disabled={isPending}
            >
              Keep appointment
            </Button>
            <Button
              variant="destructive"
              onClick={() => cancelAppointment()}
              onKeyDown={handleConfirmKeyDown}
              disabled={isPending}
            >
              {isPending && <Loader2 className="animate-spin" />}
              Cancel appointment
            </Button>
          </div>
        </div>
      )}

      {result && status === "cancelled" && !externalStillActive && (
        <p role="status" className="text-center text-sm text-muted-foreground">
          {result.message}
        </p>
      )}

      {externalStillActive && (
        <div
          className="space-y-2 rounded-lg border border-warning/50 p-3 text-sm"
          aria-busy={isPending}
        >
          <p role="status" className="text-warning">
            Cancelled in the CRM only. The Cal.com booking is still active and
            the contact was not notified.
          </p>
          {retryError && (
            <p role="alert" className="text-destructive">
              {retryError}
            </p>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={retryProviderCancel}
            disabled={isPending}
          >
            {isPending && <Loader2 className="animate-spin" />}
            Retry Cal.com cancellation
          </Button>
        </div>
      )}

      {/* Recovery path once cancelled. */}
      {status === "cancelled" && (
        <div className="flex justify-center">
          <Button onClick={onRebook}>
            <Plus />
            Rebook appointment
          </Button>
        </div>
      )}

      <dl className="grid grid-cols-[5.5rem_1fr] gap-x-3 gap-y-3 text-sm">
        <dt className={ROW_LABEL_CLASS}>What</dt>
        <dd>{appointment.service_type || "Appointment"}</dd>

        <dt className={ROW_LABEL_CLASS}>When</dt>
        <dd className="space-y-0.5">
          <p>{formatDate(start, { pattern: "EEEE, MMMM d, yyyy" })}</p>
          <p>
            {timeRangeLabel(
              appointment.scheduled_at,
              appointment.duration_minutes,
            )}
          </p>
          {tzLabel && (
            <p className="text-xs text-muted-foreground">{tzLabel}</p>
          )}
        </dd>

        <dt className={ROW_LABEL_CLASS}>Who</dt>
        <dd className="space-y-2">
          <div className="flex items-center gap-2">
            <Avatar className="size-7">
              <AvatarFallback className="text-[10px]">
                {getInitials(contact?.first_name || "", contact?.last_name)}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0">
              <p className="truncate font-medium">{getContactName(contact)}</p>
              {contactSecondary && (
                <p className="truncate text-xs text-muted-foreground">
                  {contactSecondary}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Avatar className="size-7">
              <AvatarFallback className="text-[10px]">
                {agent?.name ? getInitials(agent.name) : getInitials("")}
              </AvatarFallback>
            </Avatar>
            <div className="min-w-0">
              <p className="truncate font-medium">
                {agentId ? (agent?.name ?? "Loading…") : "Unassigned"}
              </p>
              <p className="text-xs text-muted-foreground">Agent</p>
            </div>
          </div>
        </dd>

        {depositLabel && (
          <>
            <dt className={ROW_LABEL_CLASS}>Deposit</dt>
            <dd>{depositLabel}</dd>
          </>
        )}

        <dt className={ROW_LABEL_CLASS}>Join</dt>
        <dd>
          {bookingUid ? (
            <a
              className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
              href={`https://cal.com/booking/${bookingUid}`}
              target="_blank"
              rel="noopener noreferrer"
            >
              Meeting details in Cal.com
              <ExternalLink className="size-3.5" aria-hidden="true" />
              <span className="sr-only"> (opens in a new tab)</span>
            </a>
          ) : (
            <span className="text-muted-foreground">
              Available after Cal.com sync
            </span>
          )}
        </dd>

        {status === "cancelled" && (
          <>
            <dt className={ROW_LABEL_CLASS}>Reason</dt>
            <dd className="whitespace-pre-wrap">
              {cancellationReason || "Unspecified"}
            </dd>
          </>
        )}

        {notes && (
          <>
            <dt className={ROW_LABEL_CLASS}>Details</dt>
            <dd className="whitespace-pre-wrap">{notes}</dd>
          </>
        )}
      </dl>

      {/* Operational meta kept from the previous dialog. */}
      <div className="space-y-1.5 text-xs text-muted-foreground">
        {(appointment.reminder_sent_at ||
          (appointment.reminders_sent?.length ?? 0) > 0) && (
          <div className="flex flex-wrap items-center gap-1.5">
            <ReminderBadges
              reminderSentAt={appointment.reminder_sent_at}
              remindersSent={appointment.reminders_sent}
            />
            {appointment.reminder_sent_at && (
              <span>
                Last reminder{" "}
                {formatDate(appointment.reminder_sent_at, {
                  pattern: "MMM d, h:mm a",
                })}
              </span>
            )}
          </div>
        )}
        {isScheduled && appointment.sync_status === "pending" && (
          <p className="text-warning">Not synced to Cal.com</p>
        )}
        {appointment.sync_error && (
          <p className="text-destructive">
            Sync error: {appointment.sync_error}
          </p>
        )}
        {bookingUid && <p>Cal.com booking UID: {bookingUid}</p>}
      </div>
    </>
  );
}
