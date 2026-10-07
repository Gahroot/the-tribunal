import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { NudgeCard, NudgesPage } from "@/components/nudges/nudges-page";
import type { NudgeListParams } from "@/lib/api/nudges";
import type { HumanNudge, NudgeStats, NudgeStatus } from "@/types/nudge";

const api = vi.hoisted(() => ({
  list: vi.fn(),
  getStats: vi.fn(),
  act: vi.fn(),
  dismiss: vi.fn(),
  snooze: vi.fn(),
}));

vi.mock("@/hooks/useWorkspaceId", () => ({
  useWorkspaceId: () => "workspace-1",
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

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <NudgesPage />
    </QueryClientProvider>,
  );
}

describe("NudgesPage working list", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    store = [];
    api.list.mockImplementation((_ws: string, params: NudgeListParams = {}) => {
      const scope = params.status ?? "active";
      const items = store.filter((n) =>
        scope === "active" ? n.status === "pending" || n.status === "sent" : n.status === scope,
      );
      return Promise.resolve({ items, total: items.length, page: 1, page_size: 20 });
    });
    api.getStats.mockImplementation(() => Promise.resolve(statsFor(store)));
    api.act.mockImplementation((_ws: string, id: string) => setStatus(id, "acted"));
    api.dismiss.mockImplementation((_ws: string, id: string) => setStatus(id, "dismissed"));
    api.snooze.mockImplementation((_ws: string, id: string) => setStatus(id, "snoozed"));
  });

  it("defaults to unresolved work so a delivered nudge stays visible", async () => {
    store = [makeNudge("a", "pending"), makeNudge("b", "sent"), makeNudge("c", "acted")];
    renderPage();

    expect(await screen.findByText("Nudge b")).toBeInTheDocument();
    expect(screen.getByText("Nudge a")).toBeInTheDocument();
    expect(screen.queryByText("Nudge c")).not.toBeInTheDocument();
    expect(api.list).toHaveBeenCalledWith("workspace-1", expect.objectContaining({ status: "active" }));
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

    const sentCard = (await screen.findByText("Nudge a")).closest("[data-slot='card']") as HTMLElement;
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
    expect(api.list).toHaveBeenLastCalledWith("workspace-1", expect.objectContaining({ status: "acted" }));

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
