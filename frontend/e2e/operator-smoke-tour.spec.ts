import path from "node:path";

import { expect, test, type Page, type TestInfo } from "@playwright/test";

import { hasTestUser, loginViaUI } from "./helpers";

/**
 * Durable artifacts directory for the smoke-tour screenshots. We write here
 * with an explicit path (rather than relying solely on `testInfo.attach`,
 * whose in-memory body is only embedded by the HTML reporter) so the visual
 * proof survives on disk regardless of which reporter runs. Gitignored via
 * the root `test-results/` ignore.
 */
const SCREENSHOT_DIR = path.resolve(
  process.cwd(),
  "test-results",
  "smoke-tour",
);

/**
 * Operator surfaces smoke tour.
 *
 * The Tribunal runs the prestyj Batch Video Ads sales desk autonomously; the
 * human operator only steps in for approvals and escalations. This test walks
 * the core operator surfaces the way an operator starts their day:
 *
 *   today → "Start my day" (assistant briefing) → approvals → campaigns → offers
 *
 * At each step it:
 *   1. Waits for the route's key content (its <h1>) to render.
 *   2. Asserts the page did NOT land in an error state — neither a
 *      component-level <PageErrorState> nor a Next.js error boundary
 *      (app/error.tsx / app/global-error.tsx, both of which render
 *      <PageErrorState>).
 *   3. Captures a full-page screenshot attached to the report as visual proof.
 *
 * Error detection is structural: <PageErrorState> is the only page-state slot
 * that renders an AlertCircle with `text-destructive` (loading uses a spinner
 * and empty uses an inbox icon, both `text-muted-foreground`). We additionally
 * guard against the error-boundary copy in case the markup ever changes.
 *
 * Requires a seeded test user (the prestyj workspace) — skipped otherwise so
 * the suite stays green in minimal environments.
 */

/** Locator for any visible <PageErrorState>, scoped to its destructive icon. */
function errorStateLocator(page: Page) {
  return page.locator('[data-slot="page-state"] svg.text-destructive');
}

/**
 * Assert the current page is not showing an error state, then capture a
 * full-page screenshot attached to the test report under `name`.
 */
async function captureAndAssertNoError(
  page: Page,
  testInfo: TestInfo,
  name: string,
): Promise<void> {
  // Structural check: no destructive page-state icon is rendered/visible.
  await expect(
    errorStateLocator(page),
    `${name}: a PageErrorState / error boundary is visible`,
  ).toHaveCount(0);

  // Defensive copy check: the error-boundary fallback message must be absent.
  await expect(
    page.getByText(/an unexpected error occurred/i),
    `${name}: an error-boundary fallback message is visible`,
  ).toHaveCount(0);

  const filePath = path.join(SCREENSHOT_DIR, `${name}.png`);
  const screenshot = await page.screenshot({ fullPage: true, path: filePath });
  // Attach for the HTML reporter (CI) in addition to the on-disk artifact.
  await testInfo.attach(`smoke-tour-${name}`, {
    body: screenshot,
    contentType: "image/png",
  });
}

test.describe("Operator surfaces smoke tour", () => {
  test.beforeEach(async ({ page }) => {
    test.skip(
      !hasTestUser(),
      "E2E_USER_EMAIL / E2E_USER_PASSWORD not set — skipping authenticated smoke tour",
    );
    await loginViaUI(page);
  });

  test("tours today → assistant → approvals → campaigns → offers without errors", async ({
    page,
  }, testInfo) => {
    // --- TODAY --------------------------------------------------------------
    await page.goto("/today");
    await expect(
      page.getByRole("heading", { name: "Today", level: 1 }),
    ).toBeVisible({ timeout: 15_000 });
    // The mission-queue body resolves out of its loading state.
    await expect(errorStateLocator(page)).toHaveCount(0);
    await captureAndAssertNoError(page, testInfo, "today");

    // --- START MY DAY → ASSISTANT BRIEFING ----------------------------------
    // The "Start my day" CTA links to /assistant?briefing=1 which auto-sends a
    // morning-briefing prompt. We click it the way an operator would.
    await page.getByRole("link", { name: /start my day/i }).click();
    await expect(page).toHaveURL(/\/assistant/, { timeout: 15_000 });
    await expect(
      page.getByRole("heading", { name: /crm assistant/i, level: 1 }),
    ).toBeVisible({ timeout: 15_000 });
    // The composer is the key interactive surface; confirm it rendered. We do
    // NOT wait for the AI briefing to stream — that depends on external models.
    await expect(
      page.getByPlaceholder(/ask your crm assistant/i),
    ).toBeVisible({ timeout: 15_000 });
    await captureAndAssertNoError(page, testInfo, "assistant");

    // --- APPROVALS (/pending-actions) ---------------------------------------
    await page.goto("/pending-actions");
    await expect(
      page.getByRole("heading", { name: "Pending Actions", level: 1 }),
    ).toBeVisible({ timeout: 15_000 });
    await captureAndAssertNoError(page, testInfo, "approvals");

    // --- CAMPAIGNS ----------------------------------------------------------
    await page.goto("/campaigns");
    await expect(
      page.getByRole("heading", { name: "Campaigns", level: 1 }),
    ).toBeVisible({ timeout: 15_000 });
    await captureAndAssertNoError(page, testInfo, "campaigns");

    // --- OFFERS -------------------------------------------------------------
    await page.goto("/offers");
    await expect(
      page.getByRole("heading", { name: "Offers", level: 1 }),
    ).toBeVisible({ timeout: 15_000 });
    await captureAndAssertNoError(page, testInfo, "offers");
  });
});
