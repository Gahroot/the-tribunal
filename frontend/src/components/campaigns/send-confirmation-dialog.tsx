"use client";

import { Send, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { formatNumber } from "@/lib/utils/number";

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
 * send summary and owns the single primary action of the send step.
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
}: SendConfirmationDialogProps) {
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
            Messages start going out to your selected audience as soon as the
            campaign is queued.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <dl className="space-y-2 text-sm">
            <SummaryRow label="Campaign" value={campaignName} />
            <SummaryRow label="From" value={senderLabel} />
            <SummaryRow
              label="Recipients"
              value={`${formatNumber(recipients)} contact${recipients === 1 ? "" : "s"}`}
            />
            <SummaryRow label="Schedule" value={scheduleSummary} />
            <SummaryRow label="Pace" value={paceSummary} />
          </dl>

          <div className="max-h-40 overflow-auto whitespace-pre-wrap rounded-lg border bg-muted/40 p-3 text-sm">
            {message}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" disabled={isSending} onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={onConfirm} disabled={isSending}>
            {isSending ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                Sending…
              </>
            ) : (
              <>
                <Send className="size-4" />
                Send campaign
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
