import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FindLeadsAIPage } from "@/components/contacts/find-leads-ai-page";
import { EnrichmentStatusBadge } from "@/components/contacts/shared/lead-status-badges";

const { searchMock, importMock, successMock } = vi.hoisted(() => ({
  searchMock: vi.fn(),
  importMock: vi.fn(),
  successMock: vi.fn(),
}));

vi.mock("@/hooks/useWorkspaceId", () => ({ useWorkspaceId: () => "test-workspace" }));
vi.mock("@/lib/api/find-leads-ai", () => ({
  findLeadsAIApi: { search: searchMock, importLeads: importMock },
}));
vi.mock("sonner", () => ({ toast: { success: successMock, error: vi.fn() } }));

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <FindLeadsAIPage />
    </QueryClientProvider>,
  );
}

describe("Find Leads AI optional enrichment", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    searchMock.mockResolvedValue({
      results: [
        {
          place_id: "fixture",
          name: "Fixture business",
          phone_number: "+14155552672",
          website: "https://example.com",
          has_phone: true,
          has_website: true,
          rating: null,
          review_count: 0,
          types: [],
          address: "",
          business_status: "OPERATIONAL",
        },
      ],
      total_found: 1,
      query: "plumbers",
    });
    importMock.mockResolvedValue({
      total: 1,
      imported: 1,
      rejected_low_score: 0,
      enrichment_failed: 0,
      skipped_duplicates: 0,
      skipped_no_phone: 0,
      queued_for_enrichment: 0,
      errors: [],
      lead_details: [
        {
          name: "Fixture business",
          status: "imported",
          lead_score: null,
          revenue_tier: null,
          decision_maker_name: null,
          decision_maker_title: null,
        },
      ],
    });
  });

  it("disables the threshold without resetting 80, and reports unscored imports", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.type(screen.getByPlaceholderText(/e.g., plumbers/), "plumbers");
    await user.click(screen.getByRole("button", { name: "Search" }));
    const threshold = await screen.findByRole("combobox", { name: "Min quality:" });
    expect(threshold).toHaveTextContent("Medium (80+)");
    expect(threshold).toBeEnabled();
    await user.click(screen.getByRole("checkbox", { name: "AI Enrichment" }));
    expect(threshold).toBeDisabled();
    expect(screen.getByText(/Eligible leads import unscored/)).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "AI Enrichment" }));
    expect(threshold).toBeEnabled();
    expect(threshold).toHaveTextContent("Medium (80+)");
    expect(screen.getByText(/Only leads scoring 80\+/)).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "AI Enrichment" }));
    await user.click(screen.getByRole("button", { name: "Import 1 Lead" }));
    await waitFor(() =>
      expect(importMock).toHaveBeenCalledWith(
        "test-workspace",
        expect.objectContaining({
          enable_enrichment: false,
          min_lead_score: 80,
        }),
      ),
    );
    expect(await screen.findByText("1 imported unscored")).toBeInTheDocument();
    expect(successMock).toHaveBeenCalledWith("Successfully imported 1 leads (1 unscored)");
    await user.click(screen.getByRole("button", { name: /Show details/ }));
    expect(screen.getByText("Unscored")).toBeInTheDocument();
    expect(screen.queryByText("Score: 0")).not.toBeInTheDocument();
  });

  it("labels skipped enrichment as unscored, not as a missing website", () => {
    render(<EnrichmentStatusBadge status="skipped" />);
    expect(screen.getByText("Unscored")).toBeInTheDocument();
    expect(screen.queryByText("No website")).not.toBeInTheDocument();
  });
});
