import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LeadSourcesSettingsTab } from "@/components/settings/lead-sources-settings-tab";
import type { LeadSource } from "@/lib/api/lead-sources";

const { listMock } = vi.hoisted(() => ({
  listMock: vi.fn(),
}));

vi.mock("@/hooks/useWorkspaceId", () => ({
  useWorkspaceId: () => "ws_1",
}));

vi.mock("@/components/settings/outbound-autopilot-card", () => ({
  OutboundAutopilotCard: () => null,
}));

vi.mock("@/lib/api/lead-sources", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/api/lead-sources")>(
      "@/lib/api/lead-sources",
    );
  return {
    ...actual,
    leadSourcesApi: { ...actual.leadSourcesApi, list: listMock },
  };
});

function makeSource(overrides: Partial<LeadSource>): LeadSource {
  return {
    id: "src-1",
    workspace_id: "ws_1",
    name: "Pricing Page",
    public_key: "pk_1",
    allowed_domains: ["acme.com"],
    enabled: true,
    action: "collect",
    action_config: {},
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
    endpoint_url: "https://api.test/lead-sources/pk_1",
    ...overrides,
  };
}

function renderTab() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <LeadSourcesSettingsTab />
    </QueryClientProvider>,
  );
}

describe("LeadSourcesSettingsTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the standardized empty state when there are no sources", async () => {
    listMock.mockResolvedValue([]);
    renderTab();

    expect(await screen.findByText("No lead sources yet")).toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText(/search lead sources/i),
    ).not.toBeInTheDocument();
  });

  it("filters sources with the debounced search input", async () => {
    const user = userEvent.setup();
    listMock.mockResolvedValue([
      makeSource({ id: "src-1", name: "Pricing Page", allowed_domains: ["acme.com"] }),
      makeSource({ id: "src-2", name: "Webinar Signup", allowed_domains: ["events.io"] }),
    ]);
    renderTab();

    expect(await screen.findByText("Pricing Page")).toBeInTheDocument();
    expect(screen.getByText("Webinar Signup")).toBeInTheDocument();

    const input = screen.getByPlaceholderText(/search lead sources/i);
    await user.type(input, "webinar");

    await waitFor(() =>
      expect(screen.queryByText("Pricing Page")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("Webinar Signup")).toBeInTheDocument();
  });

  it("matches on allowed domains as well as name", async () => {
    const user = userEvent.setup();
    listMock.mockResolvedValue([
      makeSource({ id: "src-1", name: "Pricing Page", allowed_domains: ["acme.com"] }),
      makeSource({ id: "src-2", name: "Webinar Signup", allowed_domains: ["events.io"] }),
    ]);
    renderTab();

    await screen.findByText("Pricing Page");
    await user.type(screen.getByPlaceholderText(/search lead sources/i), "events.io");

    await waitFor(() =>
      expect(screen.queryByText("Pricing Page")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("Webinar Signup")).toBeInTheDocument();
  });

  it("shows a no-matches empty state when the search excludes everything", async () => {
    const user = userEvent.setup();
    listMock.mockResolvedValue([
      makeSource({ id: "src-1", name: "Pricing Page", allowed_domains: ["acme.com"] }),
    ]);
    renderTab();

    await screen.findByText("Pricing Page");
    await user.type(screen.getByPlaceholderText(/search lead sources/i), "zzz");

    expect(
      await screen.findByText("No matching lead sources"),
    ).toBeInTheDocument();
  });
});
