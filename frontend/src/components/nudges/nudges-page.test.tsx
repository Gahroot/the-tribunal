import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ContactTaskSection } from "@/components/contacts/contact-sidebar/contact-task-section";
import { NudgeCard, NudgesPage } from "@/components/nudges/nudges-page";
import type { NudgeListParams } from "@/lib/api/nudges";
import { queryKeys } from "@/lib/query-keys";
import type { HumanNudge, NudgeStats, NudgeStatus } from "@/types/nudge";

const navigation = vi.hoisted(() => ({ search: "", workspaceId: "workspace-1" }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(navigation.search),
}));
vi.mock("@/lib/api/settings", () => ({
  settingsApi: { getTeamMembers: async () => [] },
}));

const api = vi.hoisted(() => ({
  list: vi.fn(),
  getStats: vi.fn(),
  act: vi.fn(),
  dismiss: vi.fn(),
  snooze: vi.fn(),
}));

vi.mock("@/hooks/useWorkspaceId", () => ({
  useWorkspaceId: () => navigation.workspaceId,
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock("@/lib/api/nudges", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/nudges")>("@/lib/api/nudges");
  return { ...actual, nudgesApi: { ...actual.nudgesApi, ...api } };
});

const baseNudge: HumanNudge = {
  id: "nudge-1",
  workspace_id: "workspace-1",
  contact_id: null,
  nudge_type: "approvals_waiting",
  title: "⏳ 5 approvals waiting",
  message: "Approve or reject them before they expire.",
  suggested_action: null,
  cta_label: "Review approvals",
  href: "/pending-actions",
  priority: "high",
  due_date: "2026-06-14T12:00:00.000Z",
  source_date_field: null,
  status: "pending",
  snoozed_until: null,
  delivered_via: null,
  delivered_at: null,
  acted_at: null,
  assigned_to_user_id: null,
  created_at: "2026-06-14T12:00:00.000Z",
  contact_name: null,
  contact_phone: null,
  contact_company: null,
};

function renderCard(nudge: HumanNudge = baseNudge) {
  return render(
    <NudgeCard
      nudge={nudge}
      onAct={vi.fn()}
      onDismiss={vi.fn()}
      onSnooze={vi.fn()}
      isActing={false}
      isDismissing={false}
    />,
  );
}

describe("NudgeCard CTA", () => {
  it("renders linked workspace CTAs instead of a fake Done action", () => {
    renderCard();

    const cta = screen.getByRole("link", { name: /review approvals/i });
    expect(cta).toHaveAttribute("href", "/pending-actions");
    expect(screen.queryByRole("button", { name: /done/i })).not.toBeInTheDocument();
  });
});

describe("NudgeCard delivery state", () => {
  it("keeps actions on a delivered (sent) nudge and labels it as still open", () => {
    renderCard({
      ...baseNudge,
      href: null,
      cta_label: null,
      status: "sent",
      delivered_via: "sms",
      delivered_at: "2026-06-14T12:30:00.000Z",
    });

    expect(screen.getByRole("button", { name: /^done$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /snooze/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /dismiss/i })).toBeInTheDocument();
    expect(screen.getByText("Notified")).toBeInTheDocument();
    expect(screen.getByText(/via sms · still open/i)).toBeInTheDocument();
  });

  it("shows completed history without actions", () => {
    renderCard({ ...baseNudge, href: null, cta_label: null, status: "acted" });

    expect(screen.queryByRole("button", { name: /^done$/i })).not.toBeInTheDocument();
    expect(screen.getByText("Done")).toBeInTheDocument();
  });
});

// In-memory stand-in for the nudges API that applies the same status scoping
// as the backend list endpoint (no status / "active" → pending + sent).
let store: HumanNudge[] = [];

function makeNudge(id: string, status: NudgeStatus): HumanNudge {
  return { ...baseNudge, id, title: `Nudge ${id}`, href: null, cta_label: null, status };
}

function statsFor(items: HumanNudge[]): NudgeStats {
  const count = (status: NudgeStatus) => items.filter((n) => n.status === status).length;
  return {
    pending: count("pending"),
    sent: count("sent"),
    acted: count("acted"),
    dismissed: count("dismissed"),
    snoozed: count("snoozed"),
    total: items.length,
  };
}

function setStatus(id: string, status: NudgeStatus) {
  store = store.map((n) => (n.id === id ? { ...n, status } : n));
  return Promise.resolve(store.find((n) => n.id === id));
}

function renderPage(withContact = false) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const tree = () => (
    <QueryClientProvider client={queryClient}>
      {withContact && <ContactTaskSection workspaceId="workspace-1" contactId={42} />}
      <NudgesPage />
    </QueryClientProvider>
  );
  const view = render(tree());
  return { ...view, queryClient, refresh: () => view.rerender(tree()) };
}

describe("NudgesPage working list", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    navigation.search = "";
    navigation.workspaceId = "workspace-1";
    store = [];
    api.list.mockImplementation((_ws: string, params: NudgeListParams = {}) => {
      const scope = params.status ?? "active";
      const items = store.filter(
        (n) =>
          (params.contact_id === undefined || n.contact_id === params.contact_id) &&
          (scope === "active" ? n.status === "pending" || n.status === "sent" : n.status === scope),
      );
      const page = params.page ?? 1;
      const pageSize = params.page_size ?? 20;
      return Promise.resolve({
        items: items.slice((page - 1) * pageSize, page * pageSize),
        total: items.length,
        page,
        page_size: pageSize,
      });
    });
    api.getStats.mockImplementation(() => Promise.resolve(statsFor(store)));
    api.act.mockImplementation((_ws: string, id: string) => setStatus(id, "acted"));
    api.dismiss.mockImplementation((_ws: string, id: string) => setStatus(id, "dismissed"));
    api.snooze.mockImplementation((_ws: string, id: string) => setStatus(id, "snoozed"));
  });

  it.each([0, 1, 2, 5, 25])(
    "counts undisplayed contact tasks for a backlog of %i",
    async (count) => {
      store = Array.from({ length: count }, (_, i) => ({
        ...makeNudge(`task-${i}`, i % 2 ? "sent" : "pending"),
        contact_id: 42,
      }));
      store.push(
        { ...makeNudge("completed", "acted"), contact_id: 42 },
        { ...makeNudge("dismissed", "dismissed"), contact_id: 42 },
        { ...makeNudge("snoozed", "snoozed"), contact_id: 42 },
        { ...makeNudge("other-contact", "pending"), contact_id: 99 },
      );
      const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={queryClient}>
          <ContactTaskSection workspaceId="workspace-1" contactId={42} />
        </QueryClientProvider>,
      );
      if (count === 0) await screen.findByText("No open tasks.");
      else await screen.findByText("Nudge task-0");
      expect(screen.queryByText("Nudge task-1")).not.toBeInTheDocument();
      expect(screen.queryByText("Nudge completed")).not.toBeInTheDocument();
      if (count > 1) {
        expect(
          screen.getByRole("link", {
            name: `+${count - 1} more open ${count === 2 ? "task" : "tasks"}`,
          }),
        ).toHaveAttribute("href", "/nudges?contact_id=42&workspace_id=workspace-1");
      } else expect(screen.queryByRole("link")).not.toBeInTheDocument();
      expect(api.list).toHaveBeenCalledWith("workspace-1", {
        contact_id: 42,
        status: "active",
        page: 1,
        page_size: 1,
      });
    },
  );

  it("paginates the contact backlog, reconciles completion/dismissal and refreshes the next task", async () => {
    navigation.search = "contact_id=42&workspace_id=workspace-1";
    store = Array.from({ length: 21 }, (_, i) => ({
      ...makeNudge(`task-${i}`, "pending"),
      contact_id: 42,
    }));
    store.push({ ...makeNudge("other-contact", "pending"), contact_id: 99 });
    const user = userEvent.setup();
    const { queryClient } = renderPage(true);
    expect(await screen.findByRole("link", { name: "+20 more open tasks" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to contact" })).toHaveAttribute(
      "href",
      "/contacts/42",
    );
    expect(screen.queryByText("Nudge other-contact")).not.toBeInTheDocument();
    expect(api.getStats).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Next" }));
    const card = (await screen.findByText("Nudge task-20")).closest(
      "[data-slot='card']",
    ) as HTMLElement;
    await user.click(within(card).getByRole("button", { name: /^done$/i }));
    await waitFor(() => expect(screen.queryByText("Nudge task-20")).not.toBeInTheDocument());
    await screen.findByText("Nudge task-19");
    expect(screen.queryByRole("button", { name: "Next" })).not.toBeInTheDocument();
    const firstCard = screen
      .getAllByText("Nudge task-0")
      .map((el) => el.closest("[data-slot='card']"))
      .find(Boolean) as HTMLElement;
    await user.click(within(firstCard).getByRole("button", { name: /dismiss/i }));
    await screen.findByRole("link", { name: "+18 more open tasks" });
    expect(screen.queryByText("Nudge task-0")).not.toBeInTheDocument();
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.nudges.all("workspace-1") });
    });
    expect(screen.getByRole("link", { name: "+18 more open tasks" })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /done/i }));
    expect(await screen.findByText("Nudge task-20")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^done$/i })).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /dismissed/i }));
    expect(await screen.findByText("Nudge task-0")).toBeInTheDocument();
    expect(api.list.mock.calls.every(([, params]) => params.contact_id === 42)).toBe(true);
  });

  it("fails closed on stale brand backlog links and resets pagination and filters for a new brand", async () => {
    navigation.search = "contact_id=42&workspace_id=workspace-1";
    store = Array.from({ length: 21 }, (_, i) => ({
      ...makeNudge(`a-${i}`, "acted"),
      contact_id: 42,
    }));
    const user = userEvent.setup();
    const view = renderPage();
    await screen.findByText("All caught up!");
    await user.click(screen.getByRole("tab", { name: /done/i }));
    await screen.findByText("Nudge a-0");
    await user.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByText("Nudge a-20");
    api.list.mockClear();
    navigation.workspaceId = "workspace-2";
    view.refresh();
    expect(screen.getByText(/not available in the current brand/i)).toBeInTheDocument();
    expect(api.list).not.toHaveBeenCalled();
    navigation.search = "";
    view.refresh();
    await waitFor(() =>
      expect(api.list).toHaveBeenCalledWith(
        "workspace-2",
        expect.objectContaining({ status: "active", page: 1 }),
      ),
    );
    expect(screen.queryByText("Nudge a-20")).not.toBeInTheDocument();
  });

  it("defaults to unresolved work so a delivered nudge stays visible", async () => {
    store = [makeNudge("a", "pending"), makeNudge("b", "sent"), makeNudge("c", "acted")];
    renderPage();

    expect(await screen.findByText("Nudge b")).toBeInTheDocument();
    expect(screen.getByText("Nudge a")).toBeInTheDocument();
    expect(screen.queryByText("Nudge c")).not.toBeInTheDocument();
    expect(api.list).toHaveBeenCalledWith(
      "workspace-1",
      expect.objectContaining({ status: "active" }),
    );
    expect(screen.getByRole("tab", { name: /needs attention/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText("2 nudges need attention")).toBeInTheDocument();
  });

  it("removes completed and dismissed nudges from active work", async () => {
    const user = userEvent.setup();
    store = [makeNudge("a", "sent"), makeNudge("b", "pending")];
    renderPage();

    const sentCard = (await screen.findByText("Nudge a")).closest(
      "[data-slot='card']",
    ) as HTMLElement;
    await user.click(within(sentCard).getByRole("button", { name: /^done$/i }));
    await waitFor(() => expect(screen.queryByText("Nudge a")).not.toBeInTheDocument());
    expect(api.act).toHaveBeenCalledWith("workspace-1", "a", undefined);

    const pendingCard = screen.getByText("Nudge b").closest("[data-slot='card']") as HTMLElement;
    await user.click(within(pendingCard).getByRole("button", { name: /dismiss/i }));
    expect(await screen.findByText("All caught up!")).toBeInTheDocument();
  });

  it("moves a snoozed delivered nudge out of active work into Snoozed", async () => {
    const user = userEvent.setup();
    store = [makeNudge("a", "sent")];
    renderPage();

    const card = (await screen.findByText("Nudge a")).closest("[data-slot='card']") as HTMLElement;
    await user.click(within(card).getByRole("button", { name: /snooze/i }));
    await user.click(await screen.findByRole("button", { name: /tomorrow/i }));

    expect(await screen.findByText("All caught up!")).toBeInTheDocument();
    expect(api.snooze).toHaveBeenCalledWith("workspace-1", "a", expect.any(String));

    await user.click(screen.getByRole("tab", { name: /snoozed/i }));
    expect(await screen.findByText("Nudge a")).toBeInTheDocument();
  });

  it("keeps finished and snoozed nudges discoverable through explicit filters", async () => {
    const user = userEvent.setup();
    store = [makeNudge("a", "acted"), makeNudge("b", "snoozed"), makeNudge("c", "dismissed")];
    renderPage();

    expect(await screen.findByText("All caught up!")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /done/i }));
    expect(await screen.findByText("Nudge a")).toBeInTheDocument();
    expect(api.list).toHaveBeenLastCalledWith(
      "workspace-1",
      expect.objectContaining({ status: "acted" }),
    );

    await user.click(screen.getByRole("tab", { name: /snoozed/i }));
    expect(await screen.findByText("Nudge b")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /dismissed/i }));
    expect(await screen.findByText("Nudge c")).toBeInTheDocument();
  });

  it("explains a truly empty workspace", async () => {
    renderPage();
    expect(await screen.findByText("No nudges yet")).toBeInTheDocument();
  });

  it("shows a retryable error instead of an empty state when the list fails", async () => {
    api.list.mockRejectedValue(new Error("boom"));
    renderPage();

    expect(await screen.findByText(/couldn't load your nudges/i)).toBeInTheDocument();
    expect(screen.queryByText("All caught up!")).not.toBeInTheDocument();
    expect(screen.queryByText("No nudges yet")).not.toBeInTheDocument();
  });
});
