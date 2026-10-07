"use client";

import { AlertTriangle, Clock, Loader2, RefreshCw, ShieldCheck } from "lucide-react";
import { useId, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  consentRecoverableContactIds,
  type RecipientEligibility,
  SMS_CONSENT_SOURCE_OPTIONS,
  type SmsConsentSource,
} from "@/lib/api/campaign-eligibility";
import { formatNumber } from "@/lib/utils/number";

export interface RecordConsentInput {
  contactIds: number[];
  source: SmsConsentSource;
}

interface RecipientEligibilityPanelProps {
  eligibility: RecipientEligibility | null;
  isLoading: boolean;
  error: string | null;
  onRetry: () => void;
  /** Recovery path: record attested consent, then re-check eligibility. */
  onRecordConsent?: (input: RecordConsentInput) => Promise<void>;
  isRecordingConsent?: boolean;
}

function plural(count: number, noun: string): string {
  return `${formatNumber(count)} ${noun}${count === 1 ? "" : "s"}`;
}

/**
 * Who a campaign will actually message, as decided by the backend's send-time
 * compliance rules. Advisory only: the launch and every send are rechecked.
 */
export function RecipientEligibilityPanel({
  eligibility,
  isLoading,
  error,
  onRetry,
  onRecordConsent,
  isRecordingConsent = false,
}: RecipientEligibilityPanelProps) {
  if (isLoading && !eligibility) {
    return (
      <div
        className="flex items-center gap-2 rounded-lg border p-3 text-sm text-muted-foreground"
        role="status"
      >
        <Loader2 className="size-4 animate-spin" />
        Checking who can be texted…
      </div>
    );
  }

  if (error || !eligibility) {
    return (
      <Alert variant="destructive">
        <AlertTriangle className="size-4" />
        <AlertTitle>Couldn&apos;t check recipients</AlertTitle>
        <AlertDescription className="space-y-2">
          <p>{error ?? "Recipient eligibility is unavailable."} Sending stays blocked until this check succeeds.</p>
          <Button size="sm" variant="outline" onClick={onRetry}>
            <RefreshCw className="size-4" />
            Try again
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  const recoverableIds = consentRecoverableContactIds(eligibility);
  const noneEligible = eligibility.eligible_count === 0;

  return (
    <div className="space-y-3" aria-live="polite">
      <dl className="grid grid-cols-3 gap-2 text-center text-sm">
        <div className="rounded-lg border p-2">
          <dt className="text-muted-foreground">Selected</dt>
          <dd className="text-lg font-semibold tabular-nums">
            {formatNumber(eligibility.selected_count)}
          </dd>
        </div>
        <div className="rounded-lg border p-2">
          <dt className="text-muted-foreground">Eligible now</dt>
          <dd
            className={`text-lg font-semibold tabular-nums ${noneEligible ? "text-destructive" : "text-success"}`}
          >
            {formatNumber(eligibility.eligible_count)}
          </dd>
        </div>
        <div className="rounded-lg border p-2">
          <dt className="text-muted-foreground">Excluded</dt>
          <dd className="text-lg font-semibold tabular-nums">
            {formatNumber(eligibility.excluded_count)}
          </dd>
        </div>
      </dl>

      {eligibility.exclusions.length > 0 && (
        <ul className="space-y-1 text-sm" aria-label="Exclusion reasons">
          {eligibility.exclusions.map((exclusion) => (
            <li key={exclusion.reason} className="flex justify-between gap-4">
              <span className="text-muted-foreground">{exclusion.label}</span>
              <span className="font-medium tabular-nums">{formatNumber(exclusion.count)}</span>
            </li>
          ))}
        </ul>
      )}

      {eligibility.deferral_label && !noneEligible && (
        <p className="flex items-start gap-2 text-sm text-muted-foreground">
          <Clock className="mt-0.5 size-4 shrink-0" />
          <span>
            Sends will wait: {eligibility.deferral_label.toLowerCase()}. Eligible
            recipients are queued, not dropped.
          </span>
        </p>
      )}

      {noneEligible ? (
        <Alert variant="destructive">
          <AlertTriangle className="size-4" />
          <AlertTitle>Nobody can be texted yet</AlertTitle>
          <AlertDescription>
            {recoverableIds.length > 0
              ? "These contacts have no SMS consent on file. If you collected consent, record it below; otherwise go back and choose a different audience."
              : "Go back and choose a different audience. Opted-out contacts are never messaged."}
          </AlertDescription>
        </Alert>
      ) : (
        eligibility.excluded_count > 0 && (
          <p className="text-sm text-muted-foreground">
            Only {plural(eligibility.eligible_count, "eligible contact")} will be
            messaged; excluded contacts are skipped and shown in campaign results.
          </p>
        )
      )}

      {eligibility.consent_required && recoverableIds.length > 0 && onRecordConsent && (
        <RecordConsentForm
          contactCount={recoverableIds.length}
          isSaving={isRecordingConsent}
          onSubmit={(source) => onRecordConsent({ contactIds: recoverableIds, source })}
        />
      )}
    </div>
  );
}

function RecordConsentForm({
  contactCount,
  isSaving,
  onSubmit,
}: {
  contactCount: number;
  isSaving: boolean;
  onSubmit: (source: SmsConsentSource) => Promise<void>;
}) {
  const [source, setSource] = useState<SmsConsentSource | "">("");
  const [attested, setAttested] = useState(false);
  const sourceId = useId();
  const attestId = useId();
  const canSave = source !== "" && attested && !isSaving;

  return (
    <details className="rounded-lg border p-3 text-sm">
      <summary className="cursor-pointer font-medium">
        Record SMS consent for {plural(contactCount, "contact")}
      </summary>
      <div className="mt-3 space-y-3">
        <p className="text-muted-foreground">
          Only record consent you actually collected. Importing a contact is not
          consent, and opted-out numbers are never changed.
        </p>
        <div className="space-y-1.5">
          <Label htmlFor={sourceId}>How was consent collected?</Label>
          <Select value={source} onValueChange={(v) => setSource(v as SmsConsentSource)}>
            <SelectTrigger id={sourceId}>
              <SelectValue placeholder="Choose a source" />
            </SelectTrigger>
            <SelectContent>
              {SMS_CONSENT_SOURCE_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-start gap-2">
          <Checkbox
            id={attestId}
            checked={attested}
            onCheckedChange={(checked) => setAttested(checked === true)}
          />
          <Label htmlFor={attestId} className="font-normal leading-snug">
            I confirm each of these contacts agreed to receive text messages from us.
          </Label>
        </div>
        <Button
          size="sm"
          disabled={!canSave}
          onClick={() => {
            if (source !== "") void onSubmit(source);
          }}
        >
          {isSaving ? <Loader2 className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
          Record consent and re-check
        </Button>
      </div>
    </details>
  );
}
