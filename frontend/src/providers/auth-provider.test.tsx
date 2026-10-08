import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LoginClient } from "@/app/login/login-client";
import type { User } from "@/lib/api/auth";
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
