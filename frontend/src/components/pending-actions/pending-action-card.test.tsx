import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PendingActionCard } from "@/components/pending-actions/pending-action-card";
import type { PendingAction } from "@/types/pending-action";

const baseAction: PendingAction = {
  id: "action-1",
  workspace_id: "workspace-1",
  agent_id: "agent-1",
  action_type: "send_sms",
  action_payload: {},
  description: "Send SMS to contact 4a7f9c2e-1234-4567-8901-abcdefabcdef",
  context: {},
  status: "pending",
  urgency: "high",
  reviewed_by_id: null,
  reviewed_at: null,
  review_channel: null,
  rejection_reason: null,
  executed_at: null,
  execution_result: null,
  expires_at: null,
  notification_sent: false,
  notification_sent_at: null,
  created_at: "2026-06-14T12:00:00.000Z",
  updated_at: "2026-06-14T12:00:00.000Z",
};

function renderCard(action: PendingAction) {
  return render(
    <PendingActionCard
      action={action}
      onApprove={vi.fn()}
      onReject={vi.fn()}
      isApproving={false}
      isRejecting={false}
    />,
  );
}

describe("PendingActionCard payload details", () => {
  it("renders send_sms recipient, contact name, and message body from action_payload", () => {
    renderCard({
      ...baseAction,
      action_payload: {
        contact_name: "Avery Johnson",
        recipient_phone_number: "+14155550123",
        from_number: "+14155550999",
        body: "Hi Avery — are you still looking for a Bay Area condo?",
      },
    });

    expect(screen.getByText("Avery Johnson")).toBeInTheDocument();
    expect(screen.getByText("+14155550123")).toBeInTheDocument();
    expect(screen.getByText("+14155550999")).toBeInTheDocument();
    expect(screen.getByText("Message to send")).toBeInTheDocument();
    expect(
      screen.getByText("Hi Avery — are you still looking for a Bay Area condo?"),
    ).toBeInTheDocument();
  });

  it("renders book_appointment recipient and appointment details", () => {
    renderCard({
      ...baseAction,
      action_type: "book_appointment",
      description: "Book appointment for contact 4a7f9c2e-1234-4567-8901-abcdefabcdef",
      action_payload: {
        name: "Morgan Lee",
        phone_number: "+14155550124",
        email: "morgan@example.com",
        date: "2026-06-20",
        time: "14:30",
        timezone: "America/Los_Angeles",
        duration_minutes: 45,
      },
    });

    expect(screen.getByText("Morgan Lee")).toBeInTheDocument();
    expect(screen.getByText("+14155550124")).toBeInTheDocument();
    expect(screen.getByText("morgan@example.com")).toBeInTheDocument();
    expect(screen.getByText("2026-06-20 14:30 America/Los_Angeles")).toBeInTheDocument();
    expect(screen.getByText("45 min")).toBeInTheDocument();
  });

  it("renders apply_tag recipient and tag details", () => {
    renderCard({
      ...baseAction,
      action_type: "apply_tag",
      description: "Apply tag to contact 4a7f9c2e-1234-4567-8901-abcdefabcdef",
      action_payload: {
        contact_name: "Sam Rivera",
        contact_phone: "+14155550125",
        tag: "hot lead",
      },
    });

    expect(screen.getByText("Sam Rivera")).toBeInTheDocument();
    expect(screen.getByText("+14155550125")).toBeInTheDocument();
    expect(screen.getByText("hot lead")).toBeInTheDocument();
  });
});
