import { apiClient, type Schemas } from "@/lib/api/_client";

/**
 * SMS campaign recipient eligibility.
 *
 * The backend evaluates the same compliance rules the campaign worker applies
 * before every send (opt-outs, SMS consent, duplicates, caps). Previews are
 * advisory only: launch rechecks them, and the worker rechecks again at send
 * time, so nothing here can bypass a safeguard.
 */
export type RecipientEligibility = Schemas["RecipientEligibilityResponse"];
export type RecipientExclusion = Schemas["RecipientExclusionResponse"];
export type RecipientEligibilityPreviewRequest =
  Schemas["RecipientEligibilityPreviewRequest"];
export type CampaignStartResponse = Schemas["CampaignStartResponse"];
export type SmsConsentRecordRequest = Schemas["SmsConsentRecordRequest"];
export type SmsConsentRecordResponse = Schemas["SmsConsentRecordResponse"];
export type SmsConsentSource = SmsConsentRecordRequest["source"];

export const SMS_CONSENT_SOURCE_OPTIONS: ReadonlyArray<{
  value: SmsConsentSource;
  label: string;
}> = [
  { value: "web_form", label: "Web or lead form opt-in" },
  { value: "paper_form", label: "Signed paper form" },
  { value: "text_keyword", label: "Texted an opt-in keyword" },
  { value: "verbal_recorded", label: "Recorded verbal consent" },
  { value: "other_documented", label: "Other documented consent" },
];

export const NO_ELIGIBLE_RECIPIENTS_CODE = "no_eligible_recipients";

export const campaignEligibilityApi = {
  preview: async (
    workspaceId: string,
    body: RecipientEligibilityPreviewRequest
  ): Promise<RecipientEligibility> => {
    return apiClient.post(
      "/api/v1/workspaces/{workspace_id}/campaigns/eligibility-preview",
      { path: { workspace_id: workspaceId }, body }
    );
  },

  forCampaign: async (
    workspaceId: string,
    campaignId: string
  ): Promise<RecipientEligibility> => {
    return apiClient.get(
      "/api/v1/workspaces/{workspace_id}/campaigns/{campaign_id}/eligibility",
      { path: { workspace_id: workspaceId, campaign_id: campaignId } }
    );
  },

  recordSmsConsent: async (
    workspaceId: string,
    body: SmsConsentRecordRequest
  ): Promise<SmsConsentRecordResponse> => {
    return apiClient.post("/api/v1/workspaces/{workspace_id}/campaigns/recipients/sms-consent", {
      path: { workspace_id: workspaceId },
      body,
    });
  },
};

function isEligibility(value: unknown): value is RecipientEligibility {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as { eligible_count?: unknown }).eligible_count === "number" &&
    Array.isArray((value as { exclusions?: unknown }).exclusions)
  );
}

/**
 * Pull the launch-time eligibility out of a `409 no_eligible_recipients`
 * start error (canonical `{code, message, details}` envelope).
 */
export function getNotSendableEligibility(err: unknown): RecipientEligibility | null {
  if (typeof err !== "object" || err === null || !("response" in err)) return null;
  const data = (err as { response?: { status?: number; data?: unknown } }).response?.data;
  if (typeof data !== "object" || data === null) return null;
  const envelope = data as { code?: unknown; details?: unknown };
  if (envelope.code !== NO_ELIGIBLE_RECIPIENTS_CODE) return null;
  return isEligibility(envelope.details) ? envelope.details : null;
}

/** Contact ids that can be recovered by recording SMS consent. */
export function consentRecoverableContactIds(eligibility: RecipientEligibility): number[] {
  return eligibility.exclusions
    .filter((exclusion) => exclusion.recoverable_with_consent)
    .flatMap((exclusion) => exclusion.contact_ids);
}
