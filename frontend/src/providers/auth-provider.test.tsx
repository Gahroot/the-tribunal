import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError } from "axios";
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LoginClient } from "@/app/login/login-client";
import type { User } from "@/lib/api/auth";
import { queryKeys } from "@/lib/query-keys";
import { AuthProvider, useAuth } from "@/providers/auth-provider";

const { getCurrentUserMock, loginApiMock, registerApiMock, pathnameRef, mockRouter } = vi.hoisted(() => ({
  getCurrentUserMock: vi.fn(),
  loginApiMock: vi.fn(),
  registerApiMock: vi.fn(),
  pathnameRef: { current: "/" },
  mockRouter: {
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  },
}));

vi.mock("@/lib/api/auth", () => ({
  getCurrentUser: getCurrentUserMock,
  login: loginApiMock,
  register: registerApiMock,
}));

vi.mock("@/lib/api", () => ({
  api: { post: vi.fn(() => Promise.resolve({})) },
  isUnauthorizedError: (error: unknown) => error instanceof AxiosError && error.response?.status === 401,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => mockRouter,
  usePathname: () => pathnameRef.current,
  useSearchParams: () => new URLSearchParams(),
}));

const USER: User = {
  id: 7,
  email: "teammate@example.com",
  full_name: "Teammate",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  default_workspace_id: null,
};

function visit(url: string) {
  window.history.replaceState({}, "", url);
  pathnameRef.current = new URL(url, "http://localhost").pathname;
}

type AuthValue = ReturnType<typeof useAuth>;
let auth: AuthValue | null = null;

function Probe({ onAuth }: { onAuth: (value: AuthValue) => void }) {
  const value = useAuth();
  useEffect(() => onAuth(value), [onAuth, value]);
  return (
    <div>
      <div data-testid="loading">{value.isLoading ? "yes" : "no"}</div>
      <div data-testid="user">{value.user?.email ?? "none"}</div>
    </div>
  );
}

function renderProvider() {
  return render(
    <AuthProvider>
      <Probe
        onAuth={(value) => {
          auth = value;
        }}
      />
    </AuthProvider>,
  );
}

const router = () => mockRouter;

beforeEach(() => {
  getCurrentUserMock.mockReset();
  loginApiMock.mockReset();
  registerApiMock.mockReset();
  router().replace.mockReset();
  auth = null;
});

afterEach(() => {
  visit("/");
});

describe("Protected session recovery (RF-004)", () => {
  it("mounts protected content only after a successful probe", async () => {
    visit("/today");
    let complete!: (user: User) => void;
    getCurrentUserMock.mockReturnValue(new Promise<User>((resolve) => { complete = resolve; }));
    renderProvider();
    expect(screen.queryByTestId("user")).not.toBeInTheDocument();
    await waitFor(() => expect(getCurrentUserMock).toHaveBeenCalledWith({ skipAuthRedirect: true }));
    await act(async () => complete(USER));
    expect(await screen.findByTestId("user")).toHaveTextContent(USER.email);
    expect(router().replace).not.toHaveBeenCalled();
  });

  it("immediately unmounts protected content on explicit sign-out", async () => {
    visit("/today");
    getCurrentUserMock.mockResolvedValue(USER);
    renderProvider();
    expect(await screen.findByTestId("user")).toHaveTextContent(USER.email);
    act(() => auth!.logout());
    expect(screen.queryByTestId("user")).not.toBeInTheDocument();
    expect(router().replace).toHaveBeenCalledWith("/login");
  });

  it("does not render cached protected data while session verification fails", async () => {
    visit("/today");
    const client = new QueryClient();
    const queryKey = queryKeys.contacts.all("fixture-workspace");
    client.setQueryData(queryKey, "Cached customer data");
    const read = vi.fn();
    function CachedContent() {
      read();
      const { data } = useQuery({ queryKey, enabled: false });
      return <div>{String(data)}</div>;
    }
    getCurrentUserMock.mockRejectedValue(new TypeError("Network failure"));
    render(<QueryClientProvider client={client}><AuthProvider><CachedContent /></AuthProvider></QueryClientProvider>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Service temporarily unavailable");
    expect(screen.queryByText("Cached customer data")).not.toBeInTheDocument();
    expect(read).not.toHaveBeenCalled();
  });

  it("redirects a confirmed final 401 without mounting protected content", async () => {
    visit("/today");
    getCurrentUserMock.mockRejectedValue(new AxiosError("Expired", undefined, undefined, undefined, {
      status: 401, data: {}, headers: {}, statusText: "Unauthorized", config: {} as never,
    }));
    renderProvider();
    await waitFor(() => expect(router().replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByTestId("user")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it.each([new TypeError("Failed to fetch"), new AxiosError("Unavailable", undefined, undefined, undefined, {
    status: 503, data: {}, headers: {}, statusText: "Unavailable", config: {} as never,
  })])("blocks protected content and recovers on explicit retry: %s", async (error) => {
    visit("/today");
    let complete!: (user: User) => void;
    getCurrentUserMock.mockRejectedValueOnce(error).mockImplementationOnce(() => new Promise<User>((resolve) => { complete = resolve; }));
    renderProvider();
    expect(await screen.findByRole("alert")).toHaveTextContent("Service temporarily unavailable");
    expect(screen.queryByTestId("user")).not.toBeInTheDocument();
    expect(router().replace).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Retry session check" }));
    expect(screen.getByRole("status")).toHaveTextContent("Checking your session");
    expect(screen.queryByTestId("user")).not.toBeInTheDocument();
    await act(async () => complete(USER));
    expect(await screen.findByTestId("user")).toHaveTextContent(USER.email);
    expect(getCurrentUserMock).toHaveBeenCalledTimes(2);
    expect(loginApiMock).not.toHaveBeenCalled();
    expect(router().replace).not.toHaveBeenCalled();
  });
});

describe("Public embed route isolation (RF-017)", () => {
  it.each([
    "/embed/agent_public_id",
    "/embed/agent_public_id/",
    "/embed/agent_public_id/chat?theme=auto&autostart=true",
    "/embed/agent_public_id/both?theme=dark",
    "/embed/agent_public_id/fullpage?theme=light",
    "/p/offers/some-offer",
    "/login",
    "/login?mode=register&redirect=%2Finvite%2Ftok_1",
    "/register",
  ])("renders anonymous public content without a session probe or redirect: %s", async (url) => {
    visit(url);
    renderProvider();
    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("no"));
    expect(screen.getByTestId("user")).toHaveTextContent("none");
    expect(getCurrentUserMock).not.toHaveBeenCalled();
    expect(router().replace).not.toHaveBeenCalled();
  });

  it.each([
    "/today",
    "/agents/agent_public_id",
    "/embed",
    "/embed/",
    "/embed/agent_public_id/settings",
    "/embed/agent_public_id/chat/private",
    "/embed/agent_public_id/fullpage/private",
    "/embed/agent_public_id/both/private",
    "/embed/agent_public_id/voice",
    "/embedded/agent_public_id",
  ])("protects non-public routes without mounting their consumers: %s", async (url) => {
    visit(url);
    getCurrentUserMock.mockRejectedValue(new AxiosError("Signed out", undefined, undefined, undefined, {
      status: 401, data: {}, headers: {}, statusText: "Unauthorized", config: {} as never,
    }));
    renderProvider();
    await waitFor(() => expect(router().replace).toHaveBeenCalledWith("/login"));
    expect(getCurrentUserMock).toHaveBeenCalledWith({ skipAuthRedirect: true });
    expect(screen.queryByTestId("user")).not.toBeInTheDocument();
  });

  it("blocks protected consumers when navigating from an anonymous embed", async () => {
    visit("/embed/agent_public_id/chat");
    const view = renderProvider();
    await waitFor(() => expect(screen.getByTestId("loading")).toHaveTextContent("no"));
    visit("/today");
    view.rerender(<AuthProvider><div>Private dashboard data</div></AuthProvider>);
    await waitFor(() => expect(router().replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("Private dashboard data")).not.toBeInTheDocument();
  });
});

describe("AuthProvider on invitation pages (RF-003)", () => {
  it("recognizes an existing session with a quiet probe", async () => {
    visit("/invite/tok_1");
    getCurrentUserMock.mockResolvedValue(USER);

    renderProvider();

    await waitFor(() => expect(screen.getByTestId("user").textContent).toBe(USER.email));
    expect(getCurrentUserMock).toHaveBeenCalledWith({ optional: true });
    expect(router().replace).not.toHaveBeenCalled();
  });

  it("keeps a signed-out visitor on the public invitation page", async () => {
    visit("/invite/tok_1");
    getCurrentUserMock.mockRejectedValue(new Error("401"));

    renderProvider();

    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("no"));
    expect(screen.getByTestId("user").textContent).toBe("none");
    expect(getCurrentUserMock).toHaveBeenCalledWith({ optional: true });
    expect(router().replace).not.toHaveBeenCalled();
  });

  it("does not probe the session on other public pages", async () => {
    visit("/p/offers/some-offer");

    renderProvider();

    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("no"));
    expect(getCurrentUserMock).not.toHaveBeenCalled();
  });
});

describe("Invited account creation (RF-001)", () => {
  function renderRegistration() {
    visit("/login?redirect=%2Finvite%2Ftok_1&mode=register");
    render(<AuthProvider><LoginClient redirectTo="/invite/tok_1" initialRegister /></AuthProvider>);
  }

  it("validates, creates an account, signs in with cookies and returns to the original invitation", async () => {
    registerApiMock.mockResolvedValue(USER);
    loginApiMock.mockResolvedValue({});
    getCurrentUserMock.mockResolvedValue(USER);
    renderRegistration();
    await userEvent.type(await screen.findByLabelText("Email"), USER.email);
    await userEvent.type(screen.getByLabelText("Password"), "short");
    await userEvent.click(screen.getByRole("button", { name: "Create Account" }));
    expect(await screen.findByText("Password must be at least 8 characters")).toBeVisible();
    expect(registerApiMock).not.toHaveBeenCalled();
    await userEvent.clear(screen.getByLabelText("Password"));
    await userEvent.type(screen.getByLabelText("Password"), "Test-password-123");
    await userEvent.click(screen.getByRole("button", { name: "Create Account" }));
    await waitFor(() => expect(router().replace).toHaveBeenCalledWith("/invite/tok_1"));
    expect(registerApiMock).toHaveBeenCalledWith({ email: USER.email, password: "Test-password-123" });
    expect(registerApiMock.mock.invocationCallOrder[0]).toBeLessThan(loginApiMock.mock.invocationCallOrder[0]!);
    expect(getCurrentUserMock).toHaveBeenCalled();
    for (const [target] of router().replace.mock.calls) expect(target).toBe("/invite/tok_1");
  });

  it("disables submission and mode switching while registration is pending", async () => {
    let complete!: (value: User) => void;
    registerApiMock.mockReturnValue(new Promise<User>((resolve) => { complete = resolve; }));
    loginApiMock.mockResolvedValue({});
    getCurrentUserMock.mockResolvedValue(USER);
    renderRegistration();
    await userEvent.type(await screen.findByLabelText("Email"), USER.email);
    await userEvent.type(screen.getByLabelText("Password"), "Test-password-123");
    await userEvent.click(screen.getByRole("button", { name: "Create Account" }));
    expect(await screen.findByRole("button", { name: "Creating account…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Already have an account? Sign in" })).toBeDisabled();
    expect(screen.getByLabelText("Email")).toBeDisabled();
    await act(async () => complete(USER));
    await waitFor(() => expect(router().replace).toHaveBeenCalledWith("/invite/tok_1"));
  });

  it("shows server failure and retries without losing the invitation", async () => {
    registerApiMock.mockRejectedValueOnce({ response: { data: { detail: "Please try again" } } }).mockResolvedValue(USER);
    loginApiMock.mockResolvedValue({});
    getCurrentUserMock.mockResolvedValue(USER);
    renderRegistration();
    await userEvent.type(await screen.findByLabelText("Email"), USER.email);
    await userEvent.type(screen.getByLabelText("Password"), "Test-password-123");
    await userEvent.click(screen.getByRole("button", { name: "Create Account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Please try again");
    expect(loginApiMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Create Account" }));
    await waitFor(() => expect(router().replace).toHaveBeenCalledWith("/invite/tok_1"));
  });

  it("retries sign-in instead of registering again when the account was already created", async () => {
    registerApiMock.mockResolvedValue(USER);
    loginApiMock.mockRejectedValueOnce(new Error("Network failure")).mockResolvedValue({});
    getCurrentUserMock.mockResolvedValue(USER);
    renderRegistration();
    await userEvent.type(await screen.findByLabelText("Email"), USER.email);
    await userEvent.type(screen.getByLabelText("Password"), "Test-password-123");
    await userEvent.click(screen.getByRole("button", { name: "Create Account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Your account was created");
    await userEvent.click(screen.getByRole("button", { name: /^Sign In$/ }));
    await waitFor(() => expect(router().replace).toHaveBeenCalledWith("/invite/tok_1"));
    expect(registerApiMock).toHaveBeenCalledTimes(1);
  });
});

describe("AuthProvider login return destination (RF-003)", () => {
  it("returns to the invitation after signing in", async () => {
    visit("/login?redirect=%2Finvite%2Ftok_1");
    loginApiMock.mockResolvedValue({});
    getCurrentUserMock.mockResolvedValue(USER);

    renderProvider();
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("no"));

    await act(() =>
      auth!.login({ email: USER.email, password: "pw" }, { redirectTo: "/invite/tok_1" }),
    );

    await waitFor(() => expect(screen.getByTestId("user").textContent).toBe(USER.email));
    // Both the login call and the "already signed in on /login" effect must
    // land on the invitation — never the dashboard.
    expect(router().replace).toHaveBeenCalled();
    for (const [target] of router().replace.mock.calls) {
      expect(target).toBe("/invite/tok_1");
    }
  });

  it("falls back to the dashboard for an unsafe destination", async () => {
    visit("/login?redirect=https%3A%2F%2Fevil.example");
    loginApiMock.mockResolvedValue({});
    getCurrentUserMock.mockResolvedValue(USER);

    renderProvider();
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("no"));

    await act(() =>
      auth!.login({ email: USER.email, password: "pw" }, { redirectTo: "//evil.example" }),
    );

    await waitFor(() => expect(router().replace).toHaveBeenCalled());
    for (const [target] of router().replace.mock.calls) {
      expect(target).toBe("/");
    }
  });

  it("signs out to the sign-in page while keeping the invitation destination", async () => {
    visit("/invite/tok_1");
    getCurrentUserMock.mockResolvedValue(USER);

    renderProvider();
    await waitFor(() => expect(screen.getByTestId("user").textContent).toBe(USER.email));

    act(() => auth!.logout({ redirectTo: "/invite/tok_1" }));

    expect(router().replace).toHaveBeenCalledWith("/login?redirect=%2Finvite%2Ftok_1");
  });
});
