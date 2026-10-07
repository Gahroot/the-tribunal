import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SendConfirmationDialog } from "@/components/campaigns/send-confirmation-dialog";
import type { RecipientEligibility } from "@/lib/api/campaign-eligibility";

function eligibility(overrides: Partial<RecipientEligibility> = {}): RecipientEligibility {
  return {
    channel: "sms",
    consent_required: true,
    checked_at: "2026-10-07T12:00:00Z",
    selected_count: 4,
    eligible_count: 2,
    excluded_count: 2,
    already_contacted_count: 0,
    ready_to_send: true,
    exclusions: [
      {
        reason: "missing_sms_consent",
        label: "No SMS consent on file",
        count: 1,
        contact_ids: [3],
        recoverable_with_consent: true,
      },
      {
        reason: "global_opt_out",
        label: "Opted out of texts",
        count: 1,
        contact_ids: [4],
        recoverable_with_consent: false,
      },
    ],
    deferral_reason: null,
    deferral_label: null,
    deferral_details: {},
    ...overrides,
  };
}

function renderDialog(props: Partial<React.ComponentProps<typeof SendConfirmationDialog>> = {}) {
  const onConfirm = vi.fn();
  const onChangeAudience = vi.fn();
  render(
    <SendConfirmationDialog
      open
      onOpenChange={vi.fn()}
      campaignName="Spring listings"
      senderLabel="+15550001111"
      recipients={4}
      scheduleSummary="Any hour"
      paceSummary="10 / minute"
      message="Hi {first_name}"
      isSending={false}
      onConfirm={onConfirm}
      eligibility={eligibility()}
      eligibilityLoading={false}
      eligibilityError={null}
      onRetryEligibility={vi.fn()}
      onRecordConsent={vi.fn()}
      onChangeAudience={onChangeAudience}
      {...props}
    />,
  );
  return { onConfirm, onChangeAudience };
}

describe("SendConfirmationDialog", () => {
  it("shows selected vs eligible and exclusion reasons for mixed audiences", () => {
    const { onConfirm } = renderDialog();

    expect(screen.getByText("Eligible now").nextSibling).toHaveTextContent("2");
    expect(screen.getByText("No SMS consent on file")).toBeInTheDocument();
    expect(screen.getByText("Opted out of texts")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Send to 2 contacts" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("never offers sending when nobody is eligible and points to recovery", () => {
    const { onConfirm, onChangeAudience } = renderDialog({
      eligibility: eligibility({
        eligible_count: 0,
        excluded_count: 4,
        ready_to_send: false,
        exclusions: [
          {
            reason: "missing_sms_consent",
            label: "No SMS consent on file",
            count: 4,
            contact_ids: [1, 2, 3, 4],
            recoverable_with_consent: true,
          },
        ],
      }),
    });

    expect(screen.getByText("Nobody can be texted yet")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /send/i })).not.toBeInTheDocument();
    expect(screen.getByText(/Record SMS consent for 4 contacts/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /change audience/i }));
    expect(onChangeAudience).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("blocks sending while eligibility is unknown", () => {
    renderDialog({ eligibility: null, eligibilityError: "Network down" });

    expect(screen.getByText("Couldn't check recipients")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send campaign" })).toBeDisabled();
  });
});
