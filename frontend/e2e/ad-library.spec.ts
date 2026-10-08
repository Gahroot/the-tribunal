import { expect, test } from "@playwright/test";

import { adWorkspace, discoveredAdvertiser, discoveryJob } from "@/test/fixtures/ad-library";

import { hasTestUser, loginViaUI } from "./helpers";

/**
 * Ad Library prospecting smoke test.
 *
 * Drives the ad-library UI end-to-end:
 *   1. Open /find-leads/ad-library.
 *   2. Confirm the ICP search form renders with the "consistent but not
 *      testing" toggles.
 *   3. Launch a search and confirm a job-status banner appears.
 *   4. Confirm the ranked advertiser results section + monitors panel render.
 *
 * Requires a seeded test user — skipped otherwise so the suite stays green in
 * minimal environments. To assert the ranked-results *table* (rather than the
 * empty state) seed tracked advertisers for the test user's workspace first:
 *
 *   cd backend && uv run python -m scripts.dev.seed_promote_e2e
 *
 * The results assertion below accepts either shape so the spec stays
 * deterministic whether or not advertisers are seeded.
 */

test.describe("Ad Library prospecting", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(
      !hasTestUser(),
      "E2E_USER_EMAIL / E2E_USER_PASSWORD not set — skipping authenticated ad-library flow",
    );
    await loginViaUI(page);
  });

  test("search → results → monitors render", async ({ page }) => {
    await page.goto("/find-leads/ad-library");

    await expect(
      page.getByRole("heading", { name: /ad library/i }),
    ).toBeVisible({ timeout: 15_000 });

    // ICP toggles are the product differentiator — they must be present.
    await expect(page.getByText(/long-runner/i)).toBeVisible();
    await expect(page.getByText(/no testing/i)).toBeVisible();

    // --- SEARCH -------------------------------------------------------------
    await page.getByLabel(/keyword/i).first().fill("roofing");
    await page
      .getByRole("button", { name: /search ad library/i })
      .click();

    // A job-status banner appears once the search is enqueued (pending/running
    // or a terminal state). We assert on the status card region.
    await expect(
      page.getByText(/pending|running|succeeded|failed/i).first(),
    ).toBeVisible({ timeout: 20_000 });

    // The advertiser results toolbar renders the tracked-advertiser count.
    await expect(
      page.getByText(/\d+\s+advertisers/i).first(),
    ).toBeVisible({ timeout: 15_000 });

    // The results section renders deterministically as EITHER the ranked
    // table (when advertisers are seeded) or the empty state (when not).
    const resultsTable = page.getByRole("table");
    const emptyState = page.getByText(/no tracked advertisers yet/i);
    await expect(resultsTable.or(emptyState).first()).toBeVisible({
      timeout: 15_000,
    });

    // The saved-monitors panel is part of the page.
    await expect(page.getByText(/saved monitors/i)).toBeVisible();
  });
});

// Local synthetic HTTP/job fixtures only: never enqueue a paid provider search.
for (const outcome of ["results", "empty", "failed", "cancelled"] as const) {
  test(`RF-014 first search automatically displays ${outcome} and stops polling`, async ({ page }) => {
    await page.clock.install();
    let jobReads = 0;
    let advertiserReads = 0;
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.route("**/api/v1/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      const json = (body: unknown) => route.fulfill({
        contentType: "application/json", body: JSON.stringify(body),
      });
      if (path.endsWith("/auth/me")) return json({
        id: 1, email: "fixture@example.test", first_name: "Fixture", is_active: true,
      });
      if (path.endsWith("/workspaces")) return json([{
        workspace: { id: adWorkspace, name: "Ad fixture", slug: "fixture", is_active: true, settings: {}, created_at: discoveryJob.created_at },
        role: "owner", is_default: true,
      }]);
      if (path.endsWith("/ad-library/search")) return json(discoveryJob);
      if (path.includes("/ad-library/jobs/")) {
        jobReads++;
        return json({
          ...discoveryJob,
          status: jobReads === 1 ? "running" : outcome === "failed" || outcome === "cancelled" ? outcome : "succeeded",
          discovered_count: jobReads > 1 && outcome === "results" ? 1 : 0,
          last_error: outcome === "failed" && jobReads > 1 ? "Fixture provider failed" : null,
        });
      }
      if (path.endsWith("/ad-library/advertisers")) {
        advertiserReads++;
        const items = jobReads > 1 && outcome === "results" ? [discoveredAdvertiser] : [];
        return json({ items, total: items.length, page: 1, page_size: 50, pages: items.length });
      }
      if (path.endsWith("/integrations/calcom/booking-readiness")) return json({
        ready: false, description: "Connect your calendar.", href: "/settings?tab=integrations",
      });
      if (path.endsWith("/ad-library/monitors") || path.endsWith("/integrations")) return json([]);
      if (path.includes("/count")) return json({ count: 0, total: 0 });
      if (path.includes("/subscription")) return json({ status: "active", plan: "pro" });
      return json({ items: [], total: 0, page: 1, page_size: 50, pages: 0 });
    });
    await page.goto("/find-leads/ad-library");
    await expect.poll(() => advertiserReads).toBe(1);
    expect(errors).toEqual([]);
    await expect(page.getByText("No tracked advertisers yet")).toBeVisible();
    await page.locator("#ad-search-terms").fill("roofing");
    await page.getByRole("button", { name: "Search ad library" }).click();
    await expect(page.getByText("running", { exact: true })).toBeVisible();
    await page.clock.fastForward(30_001);
    if (outcome === "results") {
      await expect(page.getByText("Fixture Roofing", { exact: true })).toBeVisible();
      await page.getByRole("checkbox", { name: "Select Fixture Roofing" }).check();
      await expect(page.getByRole("button", { name: "Add 1 to CRM" })).toBeEnabled();
    } else if (outcome === "empty") {
      await expect(page.getByText("No matching advertisers", { exact: true })).toBeVisible();
    } else {
      await expect(page.getByText(outcome === "failed"
        ? "Fixture provider failed"
        : "Search didn't complete. Run a new search above.").last()).toBeVisible();
      await expect(page.getByText("No matching advertisers")).toHaveCount(0);
    }
    expect(advertiserReads).toBe(outcome === "failed" || outcome === "cancelled" ? 1 : 2);
    expect(jobReads).toBe(2);
    await page.clock.fastForward(90_000);
    expect(jobReads).toBe(2);
    expect(advertiserReads).toBe(outcome === "failed" || outcome === "cancelled" ? 1 : 2);
    expect(errors).toEqual([]);
  });
}
