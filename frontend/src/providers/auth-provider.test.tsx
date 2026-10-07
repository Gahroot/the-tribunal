import { act, render, screen, waitFor } from "@testing-library/react";
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { User } from "@/lib/api/auth";
import { AuthProvider, useAuth } from "@/providers/auth-provider";

const { getCurrentUserMock, loginApiMock, pathnameRef, mockRouter } = vi.hoisted(() => ({
  getCurrentUserMock: vi.fn(),
  loginApiMock: vi.fn(),
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
