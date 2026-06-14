import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DealCoachCard } from "@/components/opportunities/deal-coach-card";
import type { DealCoachCard as DealCoachCardType } from "@/types";

const { coachMock, draftCoachActionMock, toastErrorMock, toastSuccessMock } = vi.hoisted(() => ({
  coachMock: vi.fn(),
  draftCoachActionMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
}));

vi.mock("@/lib/api/opportunities", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/api/opportunities")>("@/lib/api/opportunities");
  return {
    ...actual,
    opportunitiesApi: {
      ...actual.opportunitiesApi,
      coach: coachMock,
      draftCoachAction: draftCoachActionMock,
    },
  };
});

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
  },
}));

const card: DealCoachCardType = {
  opportunity_id: "opp_1",
  workspace_id: "workspace_1",
  name: "Acme Expansion",
  amount: 12000,
  currency: "USD",
  primary_contact_id: 42,
  contact_name: "Jane Doe",
  deal_health: "at_risk",
  health_score: 40,
  health_summary: "At risk — champion silent 10 days.",
  top_risk: "Champion silent 10 days",
  risk_factors: ["Champion silent 10 days"],
  next_best_action: {
    title: "Re-engage the silent champion",
    rationale: "Waiting on a reply.",
    channel: "sms",
    timing: "Today",
  },
  drafted_action: {
    action_type: "deal_coach.follow_up",
    channel: "sms",
    description: "Drafted re-engagement SMS to Jane Doe.",
    body: "Hi Jane, checking in — want me to send next steps?",
    payload: {},
  },
  signals: {
    days_since_last_contact: 10,
    days_in_stage: 5,
    lead_score: 50,
    engagement_score: 20,
    stage_name: "Proposal",
    probability: 60,
    call_count: 1,
    sms_count: 2,
    last_call_sentiment: null,
    sentiment_trend: "flat",
    objections: [],
    open_next_steps: [],
    awaiting_reply: true,
    expected_close_overdue: false,
  },
  generated_by: "heuristic",
  generated_at: "2026-06-14T12:00:00Z",
};

function renderCard() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <DealCoachCard workspaceId="workspace_1" opportunityId="opp_1" />
    </QueryClientProvider>,
  );
}

describe("DealCoachCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    coachMock.mockResolvedValue(card);
    draftCoachActionMock.mockResolvedValue({
      decision: "pending",
      pending_action_id: "action_1",
      action_type: "deal_coach.follow_up",
      description: "Drafted re-engagement SMS to Jane Doe.",
    });
  });

  it("locks the queue button and links to approval queue after a successful queue", async () => {
    const user = userEvent.setup();
    renderCard();

    const queueButton = await screen.findByRole("button", { name: /queue sms for approval/i });
    await user.click(queueButton);

    await waitFor(() => expect(draftCoachActionMock).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button", { name: /queued for approval/i })).toBeDisabled();

    const queueLink = screen.getByRole("link", { name: /view in approval queue/i });
    expect(queueLink).toHaveAttribute("href", "/pending-actions");
  });
});
