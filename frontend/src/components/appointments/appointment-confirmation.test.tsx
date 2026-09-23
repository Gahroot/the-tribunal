import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppointmentConfirmation } from "@/components/appointments/appointment-confirmation";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import type { Appointment } from "@/types";

const { updateAppointmentMock, agentGetMock, toastSuccessMock } = vi.hoisted(
  () => ({
    updateAppointmentMock: vi.fn(),
    agentGetMock: vi.fn(),
    toastSuccessMock: vi.fn(),
  }),
);

vi.mock("@/lib/api/appointments", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/lib/api/appointments")>();
  return {
    ...actual,
    appointmentsApi: {
      ...actual.appointmentsApi,
      update: updateAppointmentMock,
    },
  };
});

vi.mock("@/lib/api/agents", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/agents")>();
  return {
    ...actual,
    agentsApi: { ...actual.agentsApi, get: agentGetMock },
  };
});

vi.mock("sonner", () => ({
  toast: { success: toastSuccessMock, error: vi.fn() },
}));

function makeAppointment(overrides: Partial<Appointment> = {}): Appointment {
  return {
    id: 7,
    contact_id: 12,
    workspace_id: "ws_1",
    agent_id: "agent-1",
    scheduled_at: "2026-10-05T15:00:00Z",
    duration_minutes: 30,
    status: "scheduled",
    service_type: "Listing consult",
    notes: "Prefers afternoon slots",
    calcom_booking_uid: "cal-uid-123",
    sync_status: "synced",
    created_at: "2026-09-01T10:00:00Z",
    updated_at: "2026-09-01T10:00:00Z",
    contact: {
      id: 12,
      user_id: 99,
      first_name: "Ava",
      last_name: "Rivera",
      email: "ava@example.com",
      phone_number: "+14155550100",
      status: "new",
      created_at: "2026-09-01T10:00:00Z",
      updated_at: "2026-09-01T10:00:00Z",
    },
    ...overrides,
  };
}

function renderConfirmation(
  appointment: Appointment,
  onRebook = vi.fn(),
  onRefresh = vi.fn(),
) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      {/* Production renders the flow inside the calendar detail dialog. */}
      <Dialog open>
        <DialogContent>
          <AppointmentConfirmation
            appointment={appointment}
            workspaceId="ws_1"
            onRefresh={onRefresh}
            onRebook={onRebook}
          />
        </DialogContent>
      </Dialog>
    </QueryClientProvider>,
  );
  return { onRebook, onRefresh };
}

describe("AppointmentConfirmation", () => {
  beforeEach(() => {
    updateAppointmentMock.mockReset().mockImplementation(
      async (_workspaceId: string, _id: number, data: Partial<Appointment>) =>
        makeAppointment({ status: "cancelled", ...data }),
    );
    agentGetMock.mockReset().mockResolvedValue({ id: 1, name: "Dana Wolfe" });
    toastSuccessMock.mockReset();
  });

  it("shows the scheduled confirmation with full meeting details", async () => {
    renderConfirmation(makeAppointment());

    expect(
      screen.getByRole("heading", { name: /this appointment is scheduled/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Listing consult")).toBeInTheDocument();
    expect(screen.getByText("Ava Rivera")).toBeInTheDocument();
    expect(
      screen.getAllByText(/ava@example\.com/).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText("Prefers afternoon slots")).toBeInTheDocument();

    // Reschedule and join links both resolve from the Cal.com booking uid.
    const reschedule = screen.getByRole("link", { name: /reschedule/i });
    expect(reschedule).toHaveAttribute(
      "href",
      "https://cal.com/reschedule/cal-uid-123",
    );
    const join = screen.getByRole("link", { name: /meeting details in cal\.com/i });
    expect(join).toHaveAttribute(
      "href",
      "https://cal.com/booking/cal-uid-123",
    );

    // Agent resolves through the detail query.
    expect(await screen.findByText("Dana Wolfe")).toBeInTheDocument();

    // Reschedule and cancel actions sit together in one rail.
    expect(
      screen.getByRole("button", { name: /cancel appointment/i }),
    ).toBeInTheDocument();
  });

  it("disables reschedule and hides join details until Cal.com sync", () => {
    renderConfirmation(
      makeAppointment({ calcom_booking_uid: undefined, sync_status: "pending" }),
    );

    expect(
      screen.getByRole("button", { name: /reschedule/i }),
    ).toBeDisabled();
    expect(screen.getByText("Available after Cal.com sync")).toBeInTheDocument();
    expect(
      screen.getByText(/not synced to cal\.com yet/i),
    ).toBeInTheDocument();
  });

  it("moves focus into the inline confirmation, and Escape/keep returns it", async () => {
    const user = userEvent.setup();
    renderConfirmation(makeAppointment());

    const cancelTrigger = screen.getByRole("button", {
      name: /cancel appointment/i,
    });
    await user.click(cancelTrigger);

    // Focus lands on the confirmation heading so its question is announced.
    const heading = screen.getByRole("heading", {
      name: /cancel this appointment\?/i,
    });
    expect(heading).toHaveFocus();

    const reason = screen.getByLabelText(/reason \(optional\)/i);
    await user.type(reason, "Client asked to move");

    // Escape inside the confirmation backs out without closing the flow.
    await user.keyboard("{Escape}");
    expect(
      screen.queryByRole("heading", { name: /cancel this appointment\?/i }),
    ).toBeNull();
    expect(
      screen.getByRole("button", { name: /cancel appointment/i }),
    ).toHaveFocus();
    expect(updateAppointmentMock).not.toHaveBeenCalled();

    // "Keep appointment" follows the same focus-return contract.
    await user.click(screen.getByRole("button", { name: /cancel appointment/i }));
    await user.click(screen.getByRole("button", { name: /keep appointment/i }));
    expect(
      screen.getByRole("button", { name: /cancel appointment/i }),
    ).toHaveFocus();
    expect(updateAppointmentMock).not.toHaveBeenCalled();
  });

  it("cancels with the typed reason and settles into the cancelled state", async () => {
    const user = userEvent.setup();
    const { onRebook, onRefresh } = renderConfirmation(makeAppointment());

    await user.click(
      screen.getByRole("button", { name: /cancel appointment/i }),
    );
    await user.type(
      screen.getByLabelText(/reason \(optional\)/i),
      "Client asked to move",
    );
    await user.click(
      screen.getByRole("button", { name: /cancel appointment/i }),
    );

    await waitFor(() =>
      expect(updateAppointmentMock).toHaveBeenCalledWith("ws_1", 7, {
        status: "cancelled",
        notes: "Client asked to move",
      }),
    );

    // Cancelled state: heading changes, focus announces it, reason is shown.
    const heading = await screen.findByRole("heading", {
      name: /this appointment is cancelled/i,
    });
    expect(heading).toHaveFocus();
    expect(screen.getByText("Client asked to move")).toBeInTheDocument();
    expect(toastSuccessMock).toHaveBeenCalledWith("Appointment cancelled");
    expect(onRefresh).toHaveBeenCalled();

    // Recovery action is offered; reschedule/cancel rail is gone.
    expect(
      screen.queryByRole("button", { name: /cancel appointment/i }),
    ).toBeNull();
    await user.click(
      screen.getByRole("button", { name: /rebook appointment/i }),
    );
    expect(onRebook).toHaveBeenCalled();
  });

  it("shows Unspecified for a webhook-cancelled appointment without a reason", () => {
    // Mirrors the Cal.com BOOKING_CANCELLED webhook-driven status: the backend
    // stores status but no dedicated cancellation-reason field.
    renderConfirmation(
      makeAppointment({ status: "cancelled", notes: undefined }),
    );

    expect(
      screen.getByRole("heading", { name: /this appointment is cancelled/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Unspecified")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /rebook appointment/i }),
    ).toBeInTheDocument();
  });
});
