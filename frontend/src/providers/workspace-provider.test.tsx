import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NoWorkspaceGate } from "@/components/workspaces/no-workspace-gate";
import type { WorkspaceWithMembership } from "@/lib/api/workspaces";
import { WorkspaceProvider, useWorkspace } from "@/providers/workspace-provider";

// --- Hoisted mocks -------------------------------------------------------

const { listMock, useAuthMock } = vi.hoisted(() => ({
  listMock: vi.fn<() => Promise<WorkspaceWithMembership[]>>(),
  useAuthMock: vi.fn(),
}));

vi.mock("@/lib/api/workspaces", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/workspaces")>(
    "@/lib/api/workspaces",
  );
  return {
    ...actual,
    workspacesApi: { ...actual.workspacesApi, list: listMock },
  };
});

vi.mock("@/providers/auth-provider", () => ({
  useAuth: () => useAuthMock(),
}));

// --- Fixtures ------------------------------------------------------------

const makeWorkspace = (
  id: string,
  overrides: Partial<WorkspaceWithMembership> = {},
): WorkspaceWithMembership => ({
  workspace: {
    id,
    name: `ws-${id}`,
    slug: `ws-${id}`,
    description: null,
    settings: {},
    autonomy_mandate: {
      version: 1,
      enabled: true,
      posture: "act_and_report",
      auto_send_first_touches: true,
      auto_close_batch_packs: true,
      default_offer_id: null,
      description: null,
      batch_pack_anchor_key: "anchor_500",
      batch_pack_max_price_cents: 399700,
      allowed_batch_packs: [
        { pack_key: "anchor_500", label: "500 ads", ad_count: 500, price_cents: 250000 },
      ],
      daily_send_cap: 100,
      quiet_hours: { enabled: true, timezone: "America/New_York", start: "20:00", end: "08:00" },
      escalation_rules: [],
      operator_report: { enabled: true, channel: "sms", phone: null, events: [] },
    },
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  role: "owner",
  is_default: false,
  ...overrides,
});

const WORKSPACES: WorkspaceWithMembership[] = [
  makeWorkspace("ws_a"),
  makeWorkspace("ws_b", { is_default: true }),
  makeWorkspace("ws_c"),
];

// --- Harness -------------------------------------------------------------

function Probe() {
  const {
    currentWorkspaceId,
    workspaces,
    setCurrentWorkspace,
    isPending,
    status,
    refreshFailed,
    retry,
  } = useWorkspace();
  return (
    <div>
      <div data-testid="pending">{isPending ? "yes" : "no"}</div>
      <div data-testid="status">{status}</div>
      <div data-testid="refresh-failed">{refreshFailed ? "yes" : "no"}</div>
      <div data-testid="current">{currentWorkspaceId ?? "none"}</div>
      <div data-testid="count">{workspaces.length}</div>
      <button onClick={() => setCurrentWorkspace("ws_c")}>switch</button>
      <button onClick={retry}>probe-retry</button>
    </div>
  );
}

function renderWithProviders(client?: QueryClient, { gated = false } = {}) {
  const queryClient =
    client ??
    new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0, staleTime: 0 },
      },
    });

  const utils = render(
    <QueryClientProvider client={queryClient}>
      <WorkspaceProvider>
        {gated ? (
          <NoWorkspaceGate>
            <Probe />
          </NoWorkspaceGate>
        ) : (
          <Probe />
        )}
      </WorkspaceProvider>
    </QueryClientProvider>,
  );
  return { ...utils, queryClient };
}

// --- Setup ---------------------------------------------------------------

beforeEach(() => {
  listMock.mockReset();
  useAuthMock.mockReset();
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

// --- Tests ---------------------------------------------------------------

describe("WorkspaceProvider", () => {
  it("does not fetch workspaces when unauthenticated", async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: false, user: null });
    listMock.mockResolvedValue(WORKSPACES);

    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByTestId("current").textContent).toBe("none");
    });
    expect(listMock).not.toHaveBeenCalled();
  });

  it("falls back to the default workspace when no stored id is present", async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true, user: null });
    listMock.mockResolvedValue(WORKSPACES);

    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByTestId("current").textContent).toBe("ws_b");
    });
    expect(window.localStorage.getItem("current_workspace_id")).toBe("ws_b");
  });

  it("restores the stored workspace id when it matches a member workspace", async () => {
    window.localStorage.setItem("current_workspace_id", "ws_c");
    useAuthMock.mockReturnValue({ isAuthenticated: true, user: null });
    listMock.mockResolvedValue(WORKSPACES);

    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByTestId("current").textContent).toBe("ws_c");
    });
  });

  it("keeps the current brand when the default changes on refresh (RF-032/RF-033)", async () => {
    window.localStorage.setItem("current_workspace_id", "ws_c");
    useAuthMock.mockReturnValue({ isAuthenticated: true, user: null });
    listMock.mockResolvedValue(WORKSPACES);
    renderWithProviders();
    await waitFor(() => {
      expect(screen.getByTestId("current").textContent).toBe("ws_c");
    });
    listMock.mockResolvedValue([
      makeWorkspace("ws_a", { is_default: true }),
      makeWorkspace("ws_b"),
      makeWorkspace("ws_c"),
    ]);
    await userEvent.click(screen.getByRole("button", { name: "probe-retry" }));
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId("current").textContent).toBe("ws_c");
    expect(window.localStorage.getItem("current_workspace_id")).toBe("ws_c");
  });

  it("ignores a stale stored id and picks the default instead", async () => {
    window.localStorage.setItem("current_workspace_id", "ws_gone");
    useAuthMock.mockReturnValue({ isAuthenticated: true, user: null });
    listMock.mockResolvedValue(WORKSPACES);

    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByTestId("current").textContent).toBe("ws_b");
    });
    expect(window.localStorage.getItem("current_workspace_id")).toBe("ws_b");
  });

  it("falls back to the first workspace when none is marked default", async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true, user: null });
    listMock.mockResolvedValue([
      makeWorkspace("ws_only_a"),
      makeWorkspace("ws_only_b"),
    ]);

    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByTestId("current").textContent).toBe("ws_only_a");
    });
  });

  it("switches the active workspace, persists it, and clears the query cache", async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true, user: null });
    listMock.mockResolvedValue(WORKSPACES);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
    });
    const clearSpy = vi.spyOn(queryClient, "clear");

    renderWithProviders(queryClient);

    await waitFor(() => {
      expect(screen.getByTestId("current").textContent).toBe("ws_b");
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "switch" }));

    expect(screen.getByTestId("current").textContent).toBe("ws_c");
    expect(window.localStorage.getItem("current_workspace_id")).toBe("ws_c");
    expect(clearSpy).toHaveBeenCalled();
  });

  it("shows an outage with retry, not a create prompt, when the initial list request fails", async () => {
    window.localStorage.setItem("current_workspace_id", "ws_c");
    useAuthMock.mockReturnValue({ isAuthenticated: true, user: null });
    listMock.mockRejectedValue(new Error("Network Error"));

    renderWithProviders(undefined, { gated: true });

    expect(
      await screen.findByRole("heading", { name: /couldn.t load your workspaces/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    expect(screen.queryByText(/create your workspace/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /create workspace/i })).not.toBeInTheDocument();
    // The stored selection is not discarded by an outage.
    expect(window.localStorage.getItem("current_workspace_id")).toBe("ws_c");
  });

  it("recovers to the loaded workspace when retry succeeds", async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true, user: null });
    listMock
      .mockRejectedValueOnce(new Error("Network Error"))
      .mockResolvedValue(WORKSPACES);

    renderWithProviders(undefined, { gated: true });

    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: /try again/i }));

    await waitFor(() => {
      expect(screen.getByTestId("status").textContent).toBe("ready");
    });
    expect(screen.getByTestId("current").textContent).toBe("ws_b");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(listMock).toHaveBeenCalledTimes(2);
  });

  it("offers workspace creation only after a successful empty response", async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true, user: null });
    let resolveList: (value: WorkspaceWithMembership[]) => void = () => {};
    listMock.mockReturnValue(
      new Promise((resolve) => {
        resolveList = resolve;
      }),
    );

    renderWithProviders(undefined, { gated: true });

    // Loading: children (and their own skeletons) render, no create prompt.
    expect(screen.getByTestId("status").textContent).toBe("loading");
    expect(screen.queryByText(/create your workspace/i)).not.toBeInTheDocument();

    resolveList([]);

    expect(
      await screen.findByRole("heading", { name: /create your workspace/i }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create workspace/i })).toBeInTheDocument();
    expect(screen.queryByText(/couldn.t load your workspaces/i)).not.toBeInTheDocument();
  });

  it("keeps the selected workspace when a later refresh fails", async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true, user: null });
    listMock.mockResolvedValueOnce(WORKSPACES).mockRejectedValue(new Error("503"));

    renderWithProviders(undefined, { gated: true });

    await waitFor(() => {
      expect(screen.getByTestId("current").textContent).toBe("ws_b");
    });

    // Switching wipes the query cache and refetches the list; that refetch fails.
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "switch" }));

    await waitFor(() => {
      expect(screen.getByTestId("refresh-failed").textContent).toBe("yes");
    });
    expect(listMock).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId("status").textContent).toBe("ready");
    expect(screen.getByTestId("current").textContent).toBe("ws_c");
    expect(screen.getByTestId("count").textContent).toBe("3");
    expect(window.localStorage.getItem("current_workspace_id")).toBe("ws_c");
    expect(screen.getByRole("alert")).toHaveTextContent(/couldn.t refresh your workspaces/i);
    expect(screen.queryByText(/create your workspace/i)).not.toBeInTheDocument();

    // A plain retry that also fails still keeps the selection.
    await user.click(screen.getByRole("button", { name: "probe-retry" }));
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(3));
    expect(screen.getByTestId("current").textContent).toBe("ws_c");
    expect(screen.getByTestId("status").textContent).toBe("ready");
  });

  it("throws when useWorkspace is called outside the provider", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    function Orphan() {
      useWorkspace();
      return null;
    }

    expect(() => render(<Orphan />)).toThrow(
      /useWorkspace must be used within a WorkspaceProvider/,
    );

    errorSpy.mockRestore();
  });
});
