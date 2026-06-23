import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OpportunitiesBoard } from "@/components/opportunities/opportunities-board";
import type {
  OpportunitiesListResponse,
} from "@/lib/api/opportunities";
import type { Opportunity, Pipeline } from "@/types";

const { listMock, listPipelinesMock } = vi.hoisted(() => ({
  listMock: vi.fn(),
  listPipelinesMock: vi.fn(),
}));

vi.mock("@/hooks/useWorkspaceId", () => ({
  useWorkspaceId: () => "ws_1",
}));

vi.mock("@/components/opportunities/opportunity-detail-sheet", () => ({
  OpportunityDetailSheet: () => null,
}));

vi.mock("@/components/opportunities/opportunity-create-sheet", () => ({
  OpportunityCreateSheet: () => null,
}));

vi.mock("@/lib/api/opportunities", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/api/opportunities")>(
      "@/lib/api/opportunities",
    );
  return {
    ...actual,
    opportunitiesApi: {
      ...actual.opportunitiesApi,
      list: listMock,
      listPipelines: listPipelinesMock,
    },
  };
});

const pipeline: Pipeline = {
  id: "pipe-1",
  workspace_id: "ws_1",
  name: "Sales Pipeline",
  is_active: true,
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
  stages: [
    {
      id: "stage-1",
      pipeline_id: "pipe-1",
      name: "Prospecting",
      order: 0,
      probability: 10,
      stage_type: "active",
      created_at: "2026-06-01T00:00:00Z",
      updated_at: "2026-06-01T00:00:00Z",
    },
  ],
};

function makeOpp(overrides: Partial<Opportunity>): Opportunity {
  return {
    id: "opp-1",
    workspace_id: "ws_1",
    pipeline_id: "pipe-1",
    stage_id: "stage-1",
    name: "Acme Corp Deal",
    currency: "USD",
    probability: 10,
    status: "open",
    is_active: true,
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
    ...overrides,
  };
}

function listResponse(items: Opportunity[]): OpportunitiesListResponse {
  return { items, total: items.length, page: 1, page_size: 200, pages: 1 };
}

function renderBoard() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <OpportunitiesBoard />
    </QueryClientProvider>,
  );
}

describe("OpportunitiesBoard search", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listPipelinesMock.mockResolvedValue([pipeline]);
    listMock.mockResolvedValue(
      listResponse([
        makeOpp({ id: "opp-1", name: "Acme Corp Deal" }),
        makeOpp({ id: "opp-2", name: "Globex Renewal" }),
      ]),
    );
  });

  it("filters opportunity cards by the debounced search term", async () => {
    const user = userEvent.setup();
    renderBoard();

    expect(await screen.findByText("Acme Corp Deal")).toBeInTheDocument();
    expect(screen.getByText("Globex Renewal")).toBeInTheDocument();

    await user.type(
      screen.getByLabelText("Search opportunities"),
      "globex",
    );

    await waitFor(() =>
      expect(screen.queryByText("Acme Corp Deal")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("Globex Renewal")).toBeInTheDocument();
  });
});
