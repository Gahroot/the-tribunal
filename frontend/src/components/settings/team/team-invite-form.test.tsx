import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TeamInviteForm } from "@/components/settings/team/team-invite-form";
import type { InvitationResponse } from "@/lib/api/invitations";

const { listMock, resendMock, cancelMock, toastSuccessMock, toastErrorMock } = vi.hoisted(
  () => ({
    listMock: vi.fn(),
    resendMock: vi.fn(),
    cancelMock: vi.fn(),
    toastSuccessMock: vi.fn(),
    toastErrorMock: vi.fn(),
  }),
);

vi.mock("@/lib/api/invitations", () => ({
  invitationsApi: { list: listMock, resend: resendMock, cancel: cancelMock },
}));

vi.mock("sonner", () => ({
  toast: { success: toastSuccessMock, error: toastErrorMock, warning: vi.fn() },
}));

function invitation(overrides: Partial<InvitationResponse> = {}): InvitationResponse {
  return {
    id: "inv_1",
    workspace_id: "ws_1",
    email: "teammate@example.com",
    role: "member",
    status: "pending",
    message: null,
    invited_by_email: "owner@example.com",
    invited_by_name: "Owner",
    expires_at: "2026-10-14T00:00:00Z",
    created_at: "2026-10-07T00:00:00Z",
    accepted_at: null,
    is_expired: false,
    email_status: "failed",
    email_attempt_count: 1,
    email_last_attempt_at: "2026-10-07T00:00:00Z",
    email_sent_at: null,
    ...overrides,
  };
}

function renderCard() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <TeamInviteForm workspaceId="ws_1" />
    </QueryClientProvider>,
  );
}

describe("TeamInviteForm delivery status", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows each invitation's real delivery status", async () => {
    listMock.mockResolvedValue([
      invitation(),
      invitation({ id: "inv_2", email: "ok@example.com", email_status: "sent" }),
      invitation({ id: "inv_3", email: "old@example.com", is_expired: true }),
    ]);
    renderCard();

    expect(await screen.findByText("Email failed")).toBeInTheDocument();
    expect(screen.getByText("Email sent")).toBeInTheDocument();
    expect(screen.getAllByText("Expired").length).toBeGreaterThan(0);
  });

  it("resends the existing invitation and reports the new outcome", async () => {
    listMock.mockResolvedValue([invitation()]);
    resendMock.mockResolvedValue(invitation({ email_status: "sent", email_attempt_count: 2 }));
    const user = userEvent.setup();
    renderCard();

    await user.click(
      await screen.findByRole("button", { name: "Resend invitation to teammate@example.com" }),
    );

    await waitFor(() => expect(resendMock).toHaveBeenCalledWith("ws_1", "inv_1"));
    await waitFor(() =>
      expect(toastSuccessMock).toHaveBeenCalledWith("Invitation emailed to teammate@example.com"),
    );
    // The list is refetched rather than a new invitation being created.
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(2));
  });

  it("does not claim success when the resend still fails", async () => {
    listMock.mockResolvedValue([invitation()]);
    resendMock.mockResolvedValue(invitation({ email_attempt_count: 2 }));
    const user = userEvent.setup();
    renderCard();

    await user.click(
      await screen.findByRole("button", { name: "Resend invitation to teammate@example.com" }),
    );

    await waitFor(() => expect(toastErrorMock).toHaveBeenCalled());
    expect(toastSuccessMock).not.toHaveBeenCalled();
  });
});
