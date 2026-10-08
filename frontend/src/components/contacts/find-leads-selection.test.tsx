import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { FindLeadsAIPage } from "@/components/contacts/find-leads-ai-page";
import { FindLeadsPage } from "@/components/contacts/find-leads-page";
import type { AIImportLeadsRequest } from "@/lib/api/find-leads-ai";
import type { BusinessResult } from "@/lib/api/scraping";
import { server } from "@/test/msw/server";

vi.mock("@/hooks/useWorkspaceId", () => ({
  useWorkspaceId: () => "fixture-workspace",
}));

function lead(placeId: string, overrides: Partial<BusinessResult> = {}): BusinessResult {
  return {
    place_id: placeId,
    name: placeId,
    address: "Austin, TX",
    phone_number: "5125550100",
    website: "https://example.test",
    rating: 4.5,
    review_count: 10,
    types: [],
    business_status: "OPERATIONAL",
    has_phone: true,
    has_website: true,
    ...overrides,
  };
}

const results = [
  lead("Local business"),
  lead("Lower-rated business", { rating: 3 }),
  lead("Toll-free business", { phone_number: "+1 (800) 555-0100" }),
  lead("No website business", { has_website: false, website: null }),
  lead("No phone business", { has_phone: false, phone_number: null }),
];

// Real pages, filters, selection controls, mutation hook and API clients; only
// HTTP is intercepted. No request can import into a real workspace.
describe.each([
  { name: "standard discovery", Page: FindLeadsPage, route: "scraping", ai: false },
  { name: "AI discovery", Page: FindLeadsAIPage, route: "find-leads-ai", ai: true },
])("RF-009: $name", ({ Page, route, ai }) => {
  async function setup() {
    const submitted: AIImportLeadsRequest[] = [];
    const path = `*/api/v1/workspaces/fixture-workspace/${route}`;
    server.use(
      http.post(`${path}/search`, () =>
        HttpResponse.json({ results, total_found: results.length, query: "businesses" }),
      ),
      http.post(`${path}/import`, async ({ request }) => {
        const body = (await request.json()) as AIImportLeadsRequest;
        submitted.push(body);
        return HttpResponse.json({
          total: body.leads.length,
          imported: body.leads.length,
          skipped_duplicates: 0,
          skipped_no_phone: 0,
          errors: [],
          rejected_low_score: 0,
          enrichment_failed: 0,
          queued_for_enrichment: 0,
          lead_details: [],
        });
      }),
    );
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <Page />
      </QueryClientProvider>,
    );
    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText(/e.g., plumbers/i), "businesses");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByText("Local business");

    async function assertImport(ids: string[]) {
      expect(screen.getByText(`${ids.length} selected`)).toBeInTheDocument();
      const button = screen.getByRole("button", {
        name: `Import ${ids.length} Lead${ids.length === 1 ? "" : "s"}`,
      });
      if (ai && ids.length > 0) {
        const enrichable = results.filter((r) => ids.includes(r.place_id) && r.has_website).length;
        if (enrichable > 0) {
          expect(screen.getByText(`${enrichable} enrichable`)).toBeInTheDocument();
        }
      }
      if (ids.length === 0) {
        expect(button).toBeDisabled();
        const before = submitted.length;
        await user.click(button);
        expect(submitted).toHaveLength(before);
        return;
      }
      const before = submitted.length;
      await user.click(button);
      await waitFor(() => expect(submitted).toHaveLength(before + 1));
      const request = submitted[before];
      expect(request.leads.map((r) => r.place_id)).toEqual(ids);
      expect(request.leads).toHaveLength(ids.length);
      expect(request.default_status).toBe("new");
      if (ai) {
        expect(request.enable_enrichment).toBe(true);
        expect(request.min_lead_score).toBe(80);
      }
      await waitFor(() => expect(button).toBeEnabled());
    }

    // The bulk checkbox is the only unnamed checkbox outside the result cards.
    function selectAll() {
      return screen.getAllByRole("checkbox").find((checkbox) =>
        checkbox.parentElement?.textContent?.includes(" selected"),
      )!;
    }

    return { user, assertImport, selectAll };
  }

  it("imports only visible auto-selections under the default filters", async () => {
    const { assertImport } = await setup();
    expect(screen.queryByText("Toll-free business")).not.toBeInTheDocument();
    expect(screen.queryByText("No phone business")).not.toBeInTheDocument();
    if (ai) expect(screen.queryByText("No website business")).not.toBeInTheDocument();
    await assertImport(ai
      ? ["Local business", "Lower-rated business"]
      : ["Local business", "Lower-rated business", "No website business"]);
  });

  it("reconciles later filter changes and individual toggles with the request", async () => {
    const { user, assertImport } = await setup();
    await user.click(screen.getByRole("checkbox", { name: "Hide 800 numbers" }));
    await assertImport(ai
      ? ["Local business", "Lower-rated business", "Toll-free business"]
      : ["Local business", "Lower-rated business", "Toll-free business", "No website business"]);
    await user.click(screen.getByText("Toll-free business"));
    await user.click(screen.getByRole("checkbox", { name: "Hide 800 numbers" }));
    // Rating narrows the audience without losing the hidden selections.
    await user.click(screen.getAllByRole("combobox")[1]);
    await user.click(screen.getByRole("option", { name: "4+" }));
    await assertImport(ai ? ["Local business"] : ["Local business", "No website business"]);
    await user.click(screen.getByText("Local business"));
    await assertImport(ai ? [] : ["No website business"]);
    // Website filters must not silently expand phone/website auto-eligibility.
    await user.click(screen.getByRole("checkbox", { name: ai ? /Has website/ : "No website" }));
    await user.click(screen.getByText("No website business"));
    await assertImport(ai ? ["No website business"] : []);
  });

  it("select-all and clear-all submit exactly the visible selection after filter changes", async () => {
    const { user, assertImport, selectAll } = await setup();
    await user.click(selectAll());
    await assertImport([]);
    await user.click(selectAll());
    await assertImport(ai
      ? ["Local business", "Lower-rated business"]
      : ["Local business", "Lower-rated business", "No website business"]);
    await user.click(screen.getByRole("checkbox", { name: "Hide 800 numbers" }));
    // Select-all did not retain the originally hidden toll-free auto-selection.
    await assertImport(ai
      ? ["Local business", "Lower-rated business"]
      : ["Local business", "Lower-rated business", "No website business"]);
    await user.click(selectAll());
    await assertImport(ai
      ? ["Local business", "Lower-rated business", "Toll-free business"]
      : ["Local business", "Lower-rated business", "Toll-free business", "No website business"]);
    await user.click(screen.getByRole("checkbox", { name: "Hide 800 numbers" }));
    await assertImport(ai
      ? ["Local business", "Lower-rated business"]
      : ["Local business", "Lower-rated business", "No website business"]);
    await user.click(selectAll());
    await user.click(screen.getByRole("checkbox", { name: "Hide 800 numbers" }));
    await assertImport([]);
  });
});
