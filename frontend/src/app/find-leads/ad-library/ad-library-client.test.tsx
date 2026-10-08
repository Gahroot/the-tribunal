import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AdLibraryJob } from "@/lib/api/ad-library";
import { queryKeys } from "@/lib/query-keys";
import { adWorkspace, discoveredAdvertiser, discoveryJob } from "@/test/fixtures/ad-library";
import { server } from "@/test/msw/server";

import { AdLibraryClient } from "./ad-library-client";

const workspace = vi.hoisted(() => ({ id: "11111111-1111-4111-8111-111111111111" }));
vi.mock("@/hooks/useWorkspaceId", () => ({ useWorkspaceId: () => workspace.id }));

afterEach(() => {
  vi.useRealTimers();
  workspace.id = adWorkspace;
});

function fixture(status: AdLibraryJob["status"], count = 0, qualified = true) {
  // Keep real React Query + HTTP; control only the polling clock.
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
  let terminal = false;
  let jobReads = 0;
  let advertiserReads = 0;
  server.use(
    http.post("*/api/v1/workspaces/:workspace/ad-library/search", () => HttpResponse.json(discoveryJob)),
    http.get("*/api/v1/workspaces/:workspace/ad-library/jobs/:job", () => {
      jobReads++;
      return HttpResponse.json({
        ...discoveryJob,
        status: terminal ? status : "running",
        discovered_count: terminal ? count : 0,
        last_error: terminal && status === "failed" ? "Fixture provider failed" : null,
      });
    }),
    http.get("*/api/v1/workspaces/:workspace/ad-library/advertisers", ({ request }) => {
      advertiserReads++;
      const onlyQualified = new URL(request.url).searchParams.get("only_qualified") === "true";
      const items = terminal && count > 0 && (!onlyQualified || qualified) ? [discoveredAdvertiser] : [];
      return HttpResponse.json({ items, total: items.length, page: 1, page_size: 50, pages: items.length });
    }),
    http.get("*/api/v1/workspaces/:workspace/ad-library/monitors", () => HttpResponse.json([])),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } });
  const otherKey = queryKeys.adLibrary.advertisers("other-workspace", { only_qualified: true });
  const unfilteredKey = queryKeys.adLibrary.advertisers(adWorkspace, { only_qualified: false, page_size: 50 });
  client.setQueryData(otherKey, { items: [], total: 0 });
  client.setQueryData(unfilteredKey, { items: [], total: 0 });
  const view = render(<QueryClientProvider client={client}><AdLibraryClient /></QueryClientProvider>);
  return {
    client, view, otherKey, unfilteredKey,
    complete: async () => {
      terminal = true;
      await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    },
    reads: () => ({ jobReads, advertiserReads }),
  };
}

async function search() {
  await screen.findByText("No tracked advertisers yet");
  fireEvent.change(screen.getByLabelText("Keyword", { selector: "#ad-search-terms" }), { target: { value: "roofing" } });
  fireEvent.click(screen.getByRole("button", { name: "Search ad library" }));
  await screen.findByText("running");
  expect(screen.getByText("Searching for advertisers…")).toBeInTheDocument();
}

async function assertStopped(reads: () => { jobReads: number; advertiserReads: number }) {
  const before = reads();
  await act(async () => { await vi.advanceTimersByTimeAsync(90_000); });
  expect(reads()).toEqual(before);
}

describe("RF-014 discovery completion", () => {
  it("refreshes an initially empty list once, including workspace filter caches, without focus or another search", async () => {
    const f = fixture("succeeded", 1);
    await search();
    expect(f.reads().advertiserReads).toBe(1);
    await f.complete();
    await screen.findByText("Fixture Roofing");
    expect(f.reads().advertiserReads).toBe(2);
    expect(f.client.getQueryState(f.unfilteredKey)?.isInvalidated).toBe(true);
    expect(f.client.getQueryState(f.otherKey)?.isInvalidated).toBe(false);
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Fixture Roofing" }));
    expect(screen.getByRole("button", { name: "Add 1 to CRM" })).toBeEnabled();
    await assertStopped(f.reads);
    expect(screen.getByRole("checkbox", { name: "Select Fixture Roofing" })).toBeChecked();
  });

  it("keeps ICP filtering and lets users reveal discovered results excluded by the filter", async () => {
    const f = fixture("succeeded", 1, false);
    await search();
    await f.complete();
    await screen.findByText("No advertisers match the ICP filter. Switch to Show all to view discovered advertisers.");
    expect(screen.queryByText("Fixture Roofing")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "ICP only" }));
    await screen.findByText("Fixture Roofing");
    expect(screen.getByRole("button", { name: "Show all" })).toBeInTheDocument();
    await assertStopped(f.reads);
  });

  it("shows genuine empty success and stops polling", async () => {
    const f = fixture("succeeded");
    await search();
    await f.complete();
    await screen.findByText("No matching advertisers");
    await waitFor(() => expect(f.reads().advertiserReads).toBe(2));
    expect(screen.queryByText("No tracked advertisers yet")).not.toBeInTheDocument();
    await assertStopped(f.reads);
  });

  it.each(["failed", "cancelled"] as const)("distinguishes %s from empty success without refreshing or polling", async (status) => {
    const f = fixture(status);
    await search();
    await f.complete();
    await screen.findByText(status);
    expect(screen.getAllByText(status === "failed" ? "Fixture provider failed" : "Search didn't complete. Run a new search above.")).toHaveLength(2);
    expect(screen.queryByText("No matching advertisers")).not.toBeInTheDocument();
    expect(f.reads().advertiserReads).toBe(1);
    await assertStopped(f.reads);
  });

  it("does not fetch an old job under a newly selected workspace", async () => {
    const f = fixture("succeeded", 1);
    await search();
    workspace.id = "other-workspace";
    f.view.rerender(<QueryClientProvider client={f.client}><AdLibraryClient /></QueryClientProvider>);
    const before = f.reads().jobReads;
    await f.complete();
    await act(async () => { await vi.advanceTimersByTimeAsync(90_000); });
    expect(f.reads().jobReads).toBe(before);
    expect(screen.queryByText("succeeded")).not.toBeInTheDocument();
  });
});
