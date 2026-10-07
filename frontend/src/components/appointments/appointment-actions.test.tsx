import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SendReminderButton } from "@/components/appointments/appointment-actions";
import type { Appointment } from "@/types";

const { sendReminderMock, toastMock } = vi.hoisted(() => ({
  sendReminderMock: vi.fn(),
  toastMock: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock("@/lib/api/appointments", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/appointments")>();
  return {
    ...actual,
    appointmentsApi: { ...actual.appointmentsApi, sendReminder: sendReminderMock },
  };
});

vi.mock("sonner", () => ({ toast: toastMock }));

const appointment = { id: 7, status: "scheduled" } as Appointment;

async function clickRemind(onSent = vi.fn()) {
  render(<SendReminderButton appointment={appointment} workspaceId="ws_1" onSent={onSent} />);
  await userEvent.click(screen.getByRole("button", { name: /remind/i }));
  await waitFor(() => expect(sendReminderMock).toHaveBeenCalled());
  return onSent;
}

describe("SendReminderButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows a provider rejection with a Try again action and does not mark sent", async () => {
    sendReminderMock
      .mockResolvedValueOnce({
        success: false,
        status: "failed",
        message: "Reminder was not sent: Invalid destination number. You can try again.",
        sent_to: null,
        retryable: true,
      })
      .mockResolvedValueOnce({
        success: true,
        status: "sent",
        message: "Reminder sent",
        sent_to: "***-***-1234",
        retryable: false,
      });

    const onSent = await clickRemind();

    await waitFor(() => expect(toastMock.error).toHaveBeenCalled());
    expect(toastMock.success).not.toHaveBeenCalled();
    expect(onSent).not.toHaveBeenCalled();
    const [message, options] = toastMock.error.mock.calls[0];
    expect(message).toContain("Invalid destination number");
    expect(options.action.label).toBe("Try again");

    await act(async () => {
      options.action.onClick();
    });
    await waitFor(() =>
      expect(toastMock.success).toHaveBeenCalledWith("Reminder sent to ***-***-1234"),
    );
    expect(sendReminderMock).toHaveBeenCalledTimes(2);
    expect(onSent).toHaveBeenCalledTimes(1);
  });

  it("shows a final failure without a retry action", async () => {
    sendReminderMock.mockResolvedValueOnce({
      success: false,
      status: "failed",
      message: "Reminder failed 5 times and was not sent.",
      sent_to: null,
      retryable: false,
    });

    const onSent = await clickRemind();

    await waitFor(() =>
      expect(toastMock.error).toHaveBeenCalledWith("Reminder failed 5 times and was not sent."),
    );
    expect(onSent).not.toHaveBeenCalled();
  });

  it("reports an earlier accepted reminder instead of claiming a new send", async () => {
    sendReminderMock.mockResolvedValueOnce({
      success: true,
      status: "already_sent",
      message: "A reminder was already sent for this appointment",
      sent_to: "***-***-1234",
      retryable: false,
    });

    await clickRemind();

    await waitFor(() =>
      expect(toastMock.info).toHaveBeenCalledWith(
        "A reminder was already sent for this appointment",
      ),
    );
    expect(toastMock.success).not.toHaveBeenCalled();
  });
});
