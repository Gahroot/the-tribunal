import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { OpportunitiesBoard } from "@/components/opportunities/opportunities-board";
import type {
  OpportunitiesListResponse,
} from "@/lib/api/opportunities";
import type { Opportunity, Pipeline } from "@/types";

const { listMock, listPipelinesMock, updateMock, toastMock } = vi.hoisted(
  () => {
    const toast = Object.assign(vi.fn(), {
      success: vi.fn(),
      error: vi.fn(),
    });
    return {
      listMock: vi.fn(),
      listPipelinesMock: vi.fn(),
      updateMock: vi.fn(),
      toastMock: toast,
    };
  },
);

vi.mock("@/hooks/useWorkspaceId", () => ({
  useWorkspaceId: () => "ws_1",
}));

vi.mock("sonner", () => ({
  toast: toastMock,
  Toaster: () => null,
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
      update: updateMock,
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
    {
      id: "stage-2",
      pipeline_id: "pipe-1",
      name: "Won",
      order: 1,
      probability: 100,
      stage_type: "won",
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
    updateMock.mockResolvedValue(undefined);
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

  it("shows a count and money total in every stage header", async () => {
    listMock.mockResolvedValue(
      listResponse([
        makeOpp({ id: "opp-1", amount: 1000 }),
        makeOpp({ id: "opp-2", name: "Globex Renewal", amount: 2500 }),
      ]),
    );
    renderBoard();

    await screen.findByText("Acme Corp Deal");
    expect(screen.getByTestId("stage-count-stage-1")).toHaveTextContent("2");
    expect(screen.getByTestId("stage-total-stage-1")).toHaveTextContent(
      "$3.5K",
    );

    // Every column gets a total, even empty ones.
    expect(screen.getByTestId("stage-count-stage-2")).toHaveTextContent("0");
    expect(screen.getByTestId("stage-total-stage-2")).toHaveTextContent("$0");
  });

  it("toggles into a list view with the same deals", async () => {
    const user = userEvent.setup();
    renderBoard();

    await screen.findByText("Acme Corp Deal");
    await user.click(screen.getByRole("button", { name: "List" }));

    expect(await screen.findByTestId("opportunity-row-opp-1")).toHaveTextContent(
      "Acme Corp Deal",
    );
    expect(
      screen.getByRole("button", { name: "List" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(
      screen.getByRole("button", { name: "Board" }),
    ).toHaveAttribute("aria-pressed", "false");

    await user.click(screen.getByRole("button", { name: "Board" }));
    expect(
      await screen.findByTestId("opportunity-card-opp-1"),
    ).toBeInTheDocument();
  });

  it("moves a deal from the actions menu and offers undo that reverts", async () => {
    const user = userEvent.setup();
    renderBoard();

    await screen.findByText("Acme Corp Deal");

    // Keyboard-accessible move path: focus the actions menu, pick a stage.
    await user.click(
      screen.getByRole("button", { name: "Actions for Acme Corp Deal" }),
    );
    await user.click(await screen.findByRole("menuitem", { name: "Won" }));

    await waitFor(() =>
      expect(updateMock).toHaveBeenCalledWith("ws_1", "opp-1", {
        stage_id: "stage-2",
      }),
    );

    // The success toast carries an Undo action pointing back at the old stage.
    await waitFor(() => expect(toastMock).toHaveBeenCalled());
    const toastCall = toastMock.mock.calls.at(-1) as [
      string,
      { action?: { label: string; onClick: () => void } },
    ];
    expect(toastCall[0]).toContain("Won");
    expect(toastCall[1].action?.label).toBe("Undo");

    toastCall[1].action?.onClick();

    await waitFor(() =>
      expect(updateMock).toHaveBeenLastCalledWith("ws_1", "opp-1", {
        stage_id: "stage-1",
      }),
    );
  });
});

describe("OpportunitiesBoard empty state", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listPipelinesMock.mockResolvedValue([]);
    listMock.mockResolvedValue(listResponse([]));
    updateMock.mockResolvedValue(undefined);
  });

  it("explains what a pipeline is and offers a Create pipeline action", async () => {
    renderBoard();

    expect(await screen.findByText("No pipeline yet")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Pipelines track opportunities from first contact to closed deal.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Create pipeline" }),
    ).toBeInTheDocument();
  });
});
