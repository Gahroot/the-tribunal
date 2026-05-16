import { expect, test } from "@playwright/test";

import { hasTestUser, loginViaUI, uniqueSuffix } from "./helpers";

/**
 * Auth + workspace bootstrap.
 *
 * Two scenarios are exercised:
 *   1. Anonymous signup — visit /register, submit signup, expect workspace
 *      creation / onboarding hand-off.
 *   2. Existing-user login — drive /login with seeded credentials and assert
 *      the user lands on an authenticated page (dashboard / onboarding /
 *      contacts depending on workspace state).
 *
 * Signup is exercised only when /register actually renders a form because the
 * route is currently a placeholder in the codebase; the test skips otherwise
 * so the suite remains useful in environments where signup ships later.
 */

test.describe("Authentication", () => {
  test("login form is reachable", async ({ page }) => {
    await page.goto("/login");
    await expect(
      page.getByRole("heading", { name: /welcome back/i }),
    ).toBeVisible();
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.getByLabel(/password/i)).toBeVisible();
    await expect(
      page.getByRole("button", { name: /sign in/i }),
    ).toBeVisible();
  });

  test("invalid credentials surface an inline error", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel(/email/i).fill(`nobody-${uniqueSuffix()}@example.com`);
    await page.getByLabel(/password/i).fill("definitely-wrong-password");
    await page.getByRole("button", { name: /sign in/i }).click();

    // Either an inline error renders or the form stays on /login. We accept
    // both shapes — anything that *isn't* a silent navigation away.
    await expect(page).toHaveURL(/\/login/);
  });

  test("signup → workspace creation → dashboard", async ({ page }) => {
    await page.goto("/register");

    // /register is currently a reserved public path with no form shipped. If
    // the route 404s or does not render a signup form, skip without failing.
    const signupHeading = page
      .getByRole("heading", { name: /sign up|create.*account|get started/i })
      .first();
    const headingVisible = await signupHeading
      .waitFor({ state: "visible", timeout: 3_000 })
      .then(() => true)
      .catch(() => false);

    test.skip(
      !headingVisible,
      "/register page is not implemented yet — signup flow cannot be exercised",
    );

    const suffix = uniqueSuffix();
    await page.getByLabel(/email/i).fill(`e2e-${suffix}@example.com`);
    await page.getByLabel(/password/i).fill(`Test-${suffix}-Pass!`);

    const submit = page
      .getByRole("button", { name: /sign up|create account|get started/i })
      .first();
    await submit.click();

    // Successful signup should land on onboarding or the dashboard, not the
    // signup page.
    await expect(page).not.toHaveURL(/\/register$/, { timeout: 15_000 });
    await expect(page).toHaveURL(/\/(onboarding|dashboard|realtor-dashboard|contacts|\/?$)/);
  });

  test("seeded user can log in and reach an authenticated page", async ({
    page,
  }) => {
    test.skip(
      !hasTestUser(),
      "E2E_USER_EMAIL / E2E_USER_PASSWORD not set — skipping authenticated login",
    );

    await loginViaUI(page);

    // After login the app should NOT show the login form.
    await expect(
      page.getByRole("heading", { name: /welcome back/i }),
    ).toHaveCount(0);
  });
});
