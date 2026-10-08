import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRouter } from "next/navigation";
import { Suspense } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { InvitationPublicResponse } from "@/lib/api/invitations";
import { queryKeys } from "@/lib/query-keys";

import InviteAcceptPage from "./page";

const { getByTokenMock, acceptMock, useAuthMock, setCurrentWorkspaceMock, logoutMock } =
  vi.hoisted(() => ({
    getByTokenMock: vi.fn(),
    acceptMock: vi.fn(),
    useAuthMock: vi.fn(),
    setCurrentWorkspaceMock: vi.fn(),
    logoutMock: vi.fn(),
  }));

vi.mock("@/lib/api/invitations", () => ({
  invitationsApi: { getByToken: getByTokenMock, accept: acceptMock },
}));

vi.mock("@/providers/auth-provider", () => ({
  useAuth: () => useAuthMock(),
}));

vi.mock("@/providers/workspace-provider", () => ({
  useWorkspace: () => ({ setCurrentWorkspace: setCurrentWorkspaceMock }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const TOKEN = "tok_abc";

const INVITATION: InvitationPublicResponse = {
  workspace_name: "Acme Realty",
  workspace_slug: "acme-realty",
  email: "teammate@example.com",
  role: "member",
  invited_by_name: "Owner",
  expires_at: "2026-12-01T00:00:00Z",
  is_expired: false,
  is_valid: true,
};

function httpError(status: number, detail = "error") {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    response: { status, data: { detail } },
  });
}

function signedIn(email = INVITATION.email) {
  useAuthMock.mockReturnValue({
    user: { id: 1, email },
    isLoading: false,
    isAuthenticated: true,
    logout: logoutMock,
  });
}

function signedOut() {
  useAuthMock.mockReturnValue({
    user: null,
    isLoading: false,
    isAuthenticated: false,
    logout: logoutMock,
  });
}

// A thenable React's `use()` reads synchronously, like Next's resolved params.
function resolvedParams<T>(value: T): Promise<T> {
  return Object.assign(Promise.resolve(value), { status: "fulfilled", value });
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <Suspense fallback={null}>
        <InviteAcceptPage params={resolvedParams({ token: TOKEN })} />
      </Suspense>
    </QueryClientProvider>,
  );
  return { queryClient };
}

// The shared next/navigation mock (src/test/setup.ts) returns one router object.
const getMockRouter = useRouter as unknown as () => {
  push: ReturnType<typeof vi.fn>;
  replace: ReturnType<typeof vi.fn>;
};
const router = () => getMockRouter();

beforeEach(() => {
  getByTokenMock.mockReset();
  acceptMock.mockReset();
  useAuthMock.mockReset();
  setCurrentWorkspaceMock.mockReset();
  logoutMock.mockReset();
  router().push.mockReset();
  router().replace.mockReset();
});

describe("Invitation page (RF-003)", () => {
  it("sends a signed-out visitor to sign in with the invitation as return path", async () => {
    signedOut();
    getByTokenMock.mockResolvedValue(INVITATION);
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "Sign in to Accept" }));

    expect(router().push).toHaveBeenCalledWith(`/login?redirect=%2Finvite%2F${TOKEN}`);
    expect(acceptMock).not.toHaveBeenCalled();
  });

  it("offers account creation without accepting and preserves the original invitation", async () => {
    signedOut();
    getByTokenMock.mockResolvedValue(INVITATION);
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "Create an Account to Accept" }));

    expect(router().push).toHaveBeenCalledWith(`/login?redirect=%2Finvite%2F${TOKEN}&mode=register`);
    expect(acceptMock).not.toHaveBeenCalled();
  });

  it("lets a signed-in invitee accept and selects the joined workspace", async () => {
    signedIn();
    getByTokenMock.mockResolvedValue(INVITATION);
    acceptMock.mockResolvedValue({
      success: true,
      message: "You have joined Acme Realty",
      workspace_id: "ws_joined",
      workspace_slug: "acme-realty",
    });
    const { queryClient } = renderPage();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    await userEvent.click(await screen.findByRole("button", { name: "Accept Invitation" }));

    await waitFor(() => expect(setCurrentWorkspaceMock).toHaveBeenCalledWith("ws_joined"));
    expect(acceptMock).toHaveBeenCalledWith(TOKEN);
    // Membership is refreshed before the joined workspace is selected.
    const refreshOrder = invalidateSpy.mock.invocationCallOrder[0];
    expect(invalidateSpy.mock.calls[0]?.[0]).toEqual({ queryKey: queryKeys.workspaces.all() });
    expect(refreshOrder).toBeLessThan(setCurrentWorkspaceMock.mock.invocationCallOrder[0]!);
    expect(router().replace).toHaveBeenCalledWith("/");
    expect(screen.getByText("You're in!")).toBeInTheDocument();
  });

  it("offers to switch accounts when signed in as someone else", async () => {
    signedIn("other@example.com");
    getByTokenMock.mockResolvedValue(INVITATION);
    renderPage();

    await userEvent.click(
      await screen.findByRole("button", { name: `Sign in as ${INVITATION.email}` }),
    );

    expect(logoutMock).toHaveBeenCalledWith({ redirectTo: `/invite/${TOKEN}` });
    expect(screen.queryByRole("button", { name: "Accept Invitation" })).not.toBeInTheDocument();
  });

  it("sends the user back through sign-in when the session lapsed during accept", async () => {
    signedIn();
    getByTokenMock.mockResolvedValue(INVITATION);
    acceptMock.mockRejectedValue(httpError(401));
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "Accept Invitation" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/session has expired/i);
    await userEvent.click(screen.getByRole("button", { name: `Sign in as ${INVITATION.email}` }));
    expect(logoutMock).toHaveBeenCalledWith({ redirectTo: `/invite/${TOKEN}` });
    expect(setCurrentWorkspaceMock).not.toHaveBeenCalled();
  });

  it("shows a retryable error when acceptance fails unexpectedly", async () => {
    signedIn();
    getByTokenMock.mockResolvedValue(INVITATION);
    acceptMock.mockRejectedValueOnce(httpError(409, "Conflict saving membership"));
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "Accept Invitation" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Conflict saving membership");
    expect(screen.getByRole("button", { name: "Try Again" })).toBeEnabled();
  });

  it("explains an invalid link", async () => {
    signedOut();
    getByTokenMock.mockRejectedValue(httpError(404, "Invitation not found"));
    renderPage();

    expect(await screen.findByText("Invalid Invitation")).toBeInTheDocument();
  });

  it("explains an expired link", async () => {
    signedIn();
    getByTokenMock.mockResolvedValue({ ...INVITATION, is_expired: true, is_valid: false });
    renderPage();

    expect(await screen.findByText("Invitation Expired")).toBeInTheDocument();
  });

  it("explains an already-used link", async () => {
    signedIn();
    getByTokenMock.mockResolvedValue({ ...INVITATION, is_valid: false });
    renderPage();

    expect(await screen.findByText("Invitation Already Used")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go to Dashboard" })).toBeInTheDocument();
  });

  it("offers a retry when the invitation cannot be loaded", async () => {
    signedOut();
    getByTokenMock.mockRejectedValueOnce(httpError(503)).mockResolvedValueOnce(INVITATION);
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "Try Again" }));

    expect(await screen.findByText("You're Invited!")).toBeInTheDocument();
  });
});
