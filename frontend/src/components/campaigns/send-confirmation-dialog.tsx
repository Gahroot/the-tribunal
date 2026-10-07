"use client";

import { Loader2, Send, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { RecipientEligibility } from "@/lib/api/campaign-eligibility";
import { formatNumber } from "@/lib/utils/number";

import {
  RecipientEligibilityPanel,
  type RecordConsentInput,
} from "./recipient-eligibility-panel";

interface SendConfirmationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  campaignName: string;
  senderLabel: string;
  recipients: number;
  scheduleSummary: string;
  paceSummary: string;
  message: string;
  isSending: boolean;
  onConfirm: () => void;
  /** Current eligibility from the backend; sending is blocked until it loads. */
  eligibility: RecipientEligibility | null;
  eligibilityLoading: boolean;
  eligibilityError: string | null;
  onRetryEligibility: () => void;
  onRecordConsent?: (input: RecordConsentInput) => Promise<void>;
  isRecordingConsent?: boolean;
  /** Recovery when nobody is eligible: return to the audience step. */
  onChangeAudience?: () => void;
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="text-right font-medium">{value}</dd>
    </div>
  );
}

/**
 * Final confirmation beat before a campaign starts sending. Shows the exact
 * send summary, who is eligible right now (and why others are excluded), and
 * owns the single primary action of the send step. The action is disabled
 * while nobody is eligible; the backend rechecks eligibility at launch.
 */
export function SendConfirmationDialog({
  open,
  onOpenChange,
  campaignName,
  senderLabel,
  recipients,
  scheduleSummary,
  paceSummary,
  message,
  isSending,
  onConfirm,
  eligibility,
  eligibilityLoading,
  eligibilityError,
  onRetryEligibility,
  onRecordConsent,
  isRecordingConsent = false,
  onChangeAudience,
}: SendConfirmationDialogProps) {
  const eligibleCount = eligibility?.eligible_count ?? 0;
  const canSend =
    !isSending &&
    !eligibilityLoading &&
    !isRecordingConsent &&
    eligibilityError === null &&
    eligibility !== null &&
    eligibleCount > 0;
  const nobodyEligible = eligibility !== null && eligibleCount === 0;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!isSending) onOpenChange(next);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Send “{campaignName}”?</DialogTitle>
          <DialogDescription>
            Messages go out only to contacts who can be texted right now, as
            soon as the campaign is queued and within its sending hours.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <dl className="space-y-2 text-sm">
            <SummaryRow label="Campaign" value={campaignName} />
            <SummaryRow label="From" value={senderLabel} />
            <SummaryRow
              label="Selected"
              value={`${formatNumber(recipients)} contact${recipients === 1 ? "" : "s"}`}
            />
            <SummaryRow label="Schedule" value={scheduleSummary} />
            <SummaryRow label="Pace" value={paceSummary} />
          </dl>

          <RecipientEligibilityPanel
            eligibility={eligibility}
            isLoading={eligibilityLoading}
            error={eligibilityError}
            onRetry={onRetryEligibility}
            onRecordConsent={onRecordConsent}
            isRecordingConsent={isRecordingConsent}
          />

          <div className="max-h-40 overflow-auto whitespace-pre-wrap rounded-lg border bg-muted/40 p-3 text-sm">
            {message}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" disabled={isSending} onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          {nobodyEligible && onChangeAudience ? (
            <Button onClick={onChangeAudience} disabled={isSending || isRecordingConsent}>
              <Users className="size-4" />
              Change audience
            </Button>
          ) : (
            <Button onClick={onConfirm} disabled={!canSend}>
              {isSending ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  Sending…
                </>
              ) : (
                <>
                  <Send className="size-4" />
                  {eligibility && eligibleCount > 0
                    ? `Send to ${formatNumber(eligibleCount)} contact${eligibleCount === 1 ? "" : "s"}`
                    : "Send campaign"}
                </>
              )}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
