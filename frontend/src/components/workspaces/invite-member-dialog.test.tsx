import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { InviteMemberDialog } from "@/components/workspaces/invite-member-dialog";
import type { InvitationResponse } from "@/lib/api/invitations";

const { createMock, resendMock, toastSuccessMock, toastErrorMock, toastWarningMock } =
  vi.hoisted(() => ({
    createMock: vi.fn(),
    resendMock: vi.fn(),
    toastSuccessMock: vi.fn(),
    toastErrorMock: vi.fn(),
    toastWarningMock: vi.fn(),
  }));

vi.mock("@/hooks/useWorkspaceId", () => ({
  useWorkspaceId: () => "ws_1",
}));

vi.mock("@/lib/api/invitations", () => ({
  invitationsApi: { create: createMock, resend: resendMock },
}));

vi.mock("sonner", () => ({
  toast: { success: toastSuccessMock, error: toastErrorMock, warning: toastWarningMock },
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
    email_status: "sent",
    email_attempt_count: 1,
    email_last_attempt_at: "2026-10-07T00:00:00Z",
    email_sent_at: "2026-10-07T00:00:00Z",
    ...overrides,
  };
}

function renderDialog() {
  const onOpenChange = vi.fn();
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <InviteMemberDialog open onOpenChange={onOpenChange} />
    </QueryClientProvider>,
  );
  return { onOpenChange };
}

async function submitInvite() {
  const user = userEvent.setup();
  await user.type(screen.getByPlaceholderText("colleague@example.com"), "teammate@example.com");
  await user.click(screen.getByRole("button", { name: "Send Invitation" }));
}

describe("InviteMemberDialog delivery reporting", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows success only when the email was actually sent", async () => {
    createMock.mockResolvedValue(invitation());
    const { onOpenChange } = renderDialog();

    await submitInvite();

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(toastSuccessMock).toHaveBeenCalledWith("Invitation emailed to teammate@example.com");
    expect(toastErrorMock).not.toHaveBeenCalled();
  });

  it("reports a failed send with a Resend action that reuses the same invitation", async () => {
    createMock.mockResolvedValue(invitation({ email_status: "failed", email_sent_at: null }));
    resendMock.mockResolvedValue(invitation({ email_attempt_count: 2 }));
    renderDialog();

    await submitInvite();

    await waitFor(() => expect(toastErrorMock).toHaveBeenCalled());
    expect(toastSuccessMock).not.toHaveBeenCalled();
    const [title, options] = toastErrorMock.mock.calls[0];
    expect(title).toContain("didn't send");
    expect(options.action.label).toBe("Resend");

    options.action.onClick();

    await waitFor(() => expect(resendMock).toHaveBeenCalledWith("ws_1", "inv_1"));
    expect(createMock).toHaveBeenCalledTimes(1);
    await waitFor(() =>
      expect(toastSuccessMock).toHaveBeenCalledWith("Invitation emailed to teammate@example.com"),
    );
  });

  it("warns when email delivery is not configured instead of claiming success", async () => {
    createMock.mockResolvedValue(
      invitation({ email_status: "not_configured", email_sent_at: null }),
    );
    renderDialog();

    await submitInvite();

    await waitFor(() => expect(toastWarningMock).toHaveBeenCalled());
    expect(toastWarningMock.mock.calls[0][0]).toContain("no email was sent");
    expect(toastSuccessMock).not.toHaveBeenCalled();
  });
});
