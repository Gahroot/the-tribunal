import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OnboardingPage from "@/app/onboarding/page";
import { SetupChecklist } from "@/components/onboarding/setup-checklist";
import { CreateWorkspaceDialog } from "@/components/workspaces/create-workspace-dialog";
import { NoWorkspaceGate } from "@/components/workspaces/no-workspace-gate";
import type { WorkspaceWithMembership } from "@/lib/api/workspaces";
import { queryKeys } from "@/lib/query-keys";
import { WorkspaceProvider, useWorkspace } from "@/providers/workspace-provider";

// --- Hoisted mocks -------------------------------------------------------

const { listMock, createMock, useAuthMock, navigation, probes, toastMock } = vi.hoisted(() => ({
  listMock: vi.fn<() => Promise<WorkspaceWithMembership[]>>(),
  createMock: vi.fn(),
  useAuthMock: vi.fn(),
  navigation: { pathname: "/", replace: vi.fn() },
  probes: { phone: vi.fn(), agent: vi.fn(), contacts: vi.fn(), calendar: vi.fn(), campaign: vi.fn() },
  toastMock: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("next/navigation", () => ({
  usePathname: () => navigation.pathname,
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ replace: navigation.replace }),
}));
vi.mock("sonner", () => ({ toast: toastMock }));
vi.mock("@/components/layout/app-sidebar", () => ({
  AppSidebar: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
vi.mock("@/lib/api/phone-numbers", () => ({ phoneNumbersApi: { list: probes.phone } }));
vi.mock("@/lib/api/agents", () => ({ agentsApi: { list: probes.agent } }));
vi.mock("@/lib/api/contacts", () => ({ contactsApi: { list: probes.contacts } }));
vi.mock("@/lib/api/integrations", () => ({ integrationsApi: { bookingReadiness: probes.calendar } }));
vi.mock("@/lib/api/campaigns", () => ({ campaignsApi: { list: probes.campaign } }));

vi.mock("@/lib/api/workspaces", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/workspaces")>(
    "@/lib/api/workspaces",
  );
  return {
    ...actual,
    workspacesApi: { ...actual.workspacesApi, list: listMock, create: createMock },
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

// Exercise the real create form, membership provider, switch boundary and
// onboarding checklist. Only network and shell chrome use local fixtures.
function CreationFlow() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Probe />
      {navigation.pathname === "/onboarding" ? <OnboardingPage /> : <SetupChecklist />}
      <button onClick={() => setOpen(true)}>Add brand</button>
      <CreateWorkspaceDialog open={open} onOpenChange={setOpen} />
    </>
  );
}

function renderCreationFlow() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const tree = () => (
    <QueryClientProvider client={client}>
      <WorkspaceProvider><CreationFlow /></WorkspaceProvider>
    </QueryClientProvider>
  );
  const view = render(tree());
  return { client, refresh: () => view.rerender(tree()) };
}

async function submitBrandB() {
  await userEvent.click(screen.getByRole("button", { name: "Add brand" }));
  await userEvent.type(screen.getByLabelText("Name *"), "Brand B");
  await userEvent.click(screen.getByRole("button", { name: "Create Workspace" }));
}

// --- Setup ---------------------------------------------------------------

beforeEach(() => {
  listMock.mockReset();
  createMock.mockReset();
  useAuthMock.mockReset();
  navigation.pathname = "/";
  navigation.replace.mockReset();
  toastMock.success.mockReset();
  toastMock.error.mockReset();
  for (const probe of Object.values(probes)) probe.mockReset();
  for (const probe of [probes.phone, probes.agent, probes.contacts, probes.campaign]) {
    probe.mockResolvedValue({ items: [], total: 0 });
  }
  probes.calendar.mockResolvedValue({ ready: false, href: "/settings?tab=integrations", description: "Connect Cal.com." });
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

  it("switches the active workspace, persists it, and removes only old-brand queries", async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true, user: null });
    listMock.mockResolvedValue(WORKSPACES);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity, staleTime: 0 } },
    });
    queryClient.setQueryData(queryKeys.contacts.all("ws_b"), { items: [] });
    queryClient.setQueryData(queryKeys.contacts.all("ws_c"), { items: ["Brand C"] });

    renderWithProviders(queryClient);

    await waitFor(() => {
      expect(screen.getByTestId("current").textContent).toBe("ws_b");
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "switch" }));

    expect(screen.getByTestId("current").textContent).toBe("ws_c");
    expect(window.localStorage.getItem("current_workspace_id")).toBe("ws_c");
    expect(queryClient.getQueryData(queryKeys.contacts.all("ws_b"))).toBeUndefined();
    expect(queryClient.getQueryData(queryKeys.contacts.all("ws_c"))).toEqual({
      items: ["Brand C"],
    });
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

    // Switching preserves the membership list; its background refresh fails.
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

  it("creates B from A, waits for membership, and enters B setup without changing A or the login default (RF-033)", async () => {
    const brandA = makeWorkspace("A", { is_default: true });
    const brandB = makeWorkspace("B");
    brandB.workspace.name = "Brand B";
    const originalA = structuredClone(brandA);
    useAuthMock.mockReturnValue({ isAuthenticated: true });
    localStorage.setItem("current_workspace_id", "A");
    navigation.pathname = "/contacts/7";
    let resolveMembership!: (list: WorkspaceWithMembership[]) => void;
    listMock.mockResolvedValueOnce([brandA]).mockImplementationOnce(() => new Promise((resolve) => { resolveMembership = resolve; }));
    createMock.mockResolvedValue(brandB.workspace);
    const { client, refresh } = renderCreationFlow();
    await waitFor(() => expect(screen.getByTestId("current")).toHaveTextContent("A"));
    await submitBrandB();
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(2));
    expect(screen.getByTestId("current")).toHaveTextContent("A");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(toastMock.success).not.toHaveBeenCalled();
    expect(navigation.replace).not.toHaveBeenCalled();
    await act(async () => resolveMembership([brandA, brandB]));
    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/onboarding", { scroll: false }));
    // The old entity route cannot start B setup requests during the handoff.
    for (const probe of Object.values(probes)) expect(probe).not.toHaveBeenCalledWith("B", expect.anything());
    expect(probes.calendar).not.toHaveBeenCalledWith("B");
    navigation.pathname = "/onboarding";
    refresh();
    expect(await screen.findByRole("heading", { name: "Finish setup: Brand B" })).toBeInTheDocument();
    expect(screen.getByTestId("current")).toHaveTextContent("B");
    await screen.findByText("0 of 5 complete");
    for (const probe of Object.values(probes)) expect(probe.mock.calls.at(-1)?.[0]).toBe("B");
    expect(localStorage.getItem("current_workspace_id")).toBe("B");
    expect(client.getQueryData(queryKeys.workspaces.all())).toEqual([originalA, brandB]);
    expect(brandA).toEqual(originalA);
    expect(createMock).toHaveBeenCalledExactlyOnceWith({ name: "Brand B", slug: "brand-b", description: undefined });
    expect(listMock).toHaveBeenCalledTimes(2);
    expect(toastMock.success).toHaveBeenCalledWith("Brand B is active. Continue setup.");
    client.clear();
  });

  it("keeps A active and the create form open when creation fails", async () => {
    useAuthMock.mockReturnValue({ isAuthenticated: true });
    listMock.mockResolvedValue([makeWorkspace("A", { is_default: true })]);
    createMock.mockRejectedValue(new Error("Create unavailable"));
    const { client } = renderCreationFlow();
    await waitFor(() => expect(screen.getByTestId("current")).toHaveTextContent("A"));
    await submitBrandB();
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith("Failed to create workspace. Please try again."));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByTestId("current")).toHaveTextContent("A");
    expect(listMock).toHaveBeenCalledTimes(1);
    expect(navigation.replace).not.toHaveBeenCalled();
    expect(toastMock.success).not.toHaveBeenCalled();
    client.clear();
  });

  it.each(["failed", "missing"])("does not claim activation when membership is %s; retries without duplicate creation", async (outcome) => {
    const brandA = makeWorkspace("A", { is_default: true });
    const brandB = makeWorkspace("B");
    brandB.workspace.name = "Brand B";
    useAuthMock.mockReturnValue({ isAuthenticated: true });
    listMock.mockResolvedValueOnce([brandA]);
    if (outcome === "failed") listMock.mockRejectedValueOnce(new Error("Refresh unavailable"));
    else listMock.mockResolvedValueOnce([brandA]);
    listMock.mockResolvedValue([brandA, brandB]);
    createMock.mockResolvedValue(brandB.workspace);
    const { client, refresh } = renderCreationFlow();
    await waitFor(() => expect(screen.getByTestId("current")).toHaveTextContent("A"));
    await submitBrandB();
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith(expect.stringContaining("Brand B was created, but could not be activated")));
    expect(screen.getByTestId("current")).toHaveTextContent("A");
    expect(localStorage.getItem("current_workspace_id")).toBe("A");
    expect(navigation.replace).not.toHaveBeenCalled();
    expect(toastMock.success).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Open setup" }));
    await waitFor(() => expect(navigation.replace).toHaveBeenCalledWith("/onboarding", { scroll: false }));
    navigation.pathname = "/onboarding";
    refresh();
    await screen.findByRole("heading", { name: "Finish setup: Brand B" });
    expect(screen.getByTestId("current")).toHaveTextContent("B");
    expect(createMock).toHaveBeenCalledTimes(1);
    expect(listMock).toHaveBeenCalledTimes(3);
    expect(brandA.is_default).toBe(true);
    client.clear();
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
