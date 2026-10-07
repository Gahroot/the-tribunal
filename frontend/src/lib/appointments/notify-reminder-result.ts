import { toast } from "sonner";

import type { SendReminderResult } from "@/lib/api/appointments";

/**
 * Show the outcome of a manual reminder. "Sent" means the SMS provider
 * accepted it; carrier delivery is not known yet. Failures that can be
 * retried get a "Try again" action.
 */
export function notifyReminderResult(
  result: SendReminderResult,
  onRetry: () => void,
): void {
  if (result.status === "already_sent") {
    toast.info(result.message || "A reminder was already sent");
    return;
  }
  if (result.success) {
    toast.success(`Reminder sent to ${result.sent_to ?? "contact"}`);
    return;
  }
  const message = result.message || "Reminder was not sent";
  if (result.retryable) {
    toast.error(message, {
      duration: 10000,
      action: { label: "Try again", onClick: onRetry },
    });
    return;
  }
  toast.error(message);
}
