import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CallOutcomeControls } from "@/components/calls/call-outcome-controls";
import type { CallOutcome } from "@/lib/api/calls";

const { getOutcomeMock, submitFeedbackMock, toastErrorMock, toastSuccessMock, updateOutcomeMock } = vi.hoisted(() => ({
  getOutcomeMock: vi.fn(),
  submitFeedbackMock: vi.fn(),
  toastErrorMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  updateOutcomeMock: vi.fn(),
}));

vi.mock("@/lib/api/calls", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/calls")>("@/lib/api/calls");
  return {
    ...actual,
    callsApi: {
      ...actual.callsApi,
      getOutcome: getOutcomeMock,
      submitFeedback: submitFeedbackMock,
      updateOutcome: updateOutcomeMock,
    },
  };
});

vi.mock("sonner", () => ({
  toast: {
    error: toastErrorMock,
    success: toastSuccessMock,
  },
}));

const outcome: CallOutcome = {
  id: "11111111-1111-1111-1111-111111111111",
  message_id: "22222222-2222-2222-2222-222222222222",
  prompt_version_id: null,
  outcome_type: "lead_qualified",
  signals: {},
  classified_by: "llm_judge",
  classification_confidence: 0.82,
  raw_hangup_cause: null,
  created_at: "2026-06-14T12:00:00Z",
  updated_at: "2026-06-14T12:00:00Z",
  call_duration_seconds: 120,
  call_direction: "outbound",
  booking_outcome: null,
};

function renderControls() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <CallOutcomeControls
        workspaceId="workspace_1"
        messageId="22222222-2222-2222-2222-222222222222"
        variant="detail"
      />
    </QueryClientProvider>,
  );
}

describe("CallOutcomeControls", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getOutcomeMock.mockResolvedValue(outcome);
    updateOutcomeMock.mockResolvedValue({
      ...outcome,
      outcome_type: "appointment_booked",
      classified_by: "user",
      classification_confidence: 1,
    });
    submitFeedbackMock.mockResolvedValue({
      id: "33333333-3333-3333-3333-333333333333",
      message_id: outcome.message_id,
      call_outcome_id: outcome.id,
      source: "user",
      user_id: 1,
      rating: null,
      thumbs: "up",
      feedback_text: null,
      feedback_signals: {},
      quality_score: null,
      quality_reasoning: null,
      created_at: "2026-06-14T12:01:00Z",
    });
  });

  it("shows the AI outcome, reclassify control, and thumbs feedback controls", async () => {
    const user = userEvent.setup();
    renderControls();

    await waitFor(() =>
      expect(screen.getByTestId("call-outcome-badge")).toHaveTextContent(
        "Outcome: Lead qualified",
      ),
    );
    expect(screen.getByLabelText("Reclassify call outcome")).toBeInTheDocument();
    expect(screen.getByTestId("call-feedback-controls")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Submit thumbs-up call feedback" }));

    await waitFor(() => expect(submitFeedbackMock).toHaveBeenCalledTimes(1));
    expect(submitFeedbackMock).toHaveBeenCalledWith(
      "workspace_1",
      "22222222-2222-2222-2222-222222222222",
      {
        source: "user",
        thumbs: "up",
        feedback_signals: {
          outcome_type: "lead_qualified",
          ui_surface: "detail",
        },
      },
    );
  });
});
