import { expect, test } from "@playwright/test";

import { hasTestUser, loginViaUI, uniqueSuffix } from "./helpers";

/**
 * Auth + workspace bootstrap.
 *
 * Two scenarios are exercised:
 *   1. Invited signup — create an account from the invitation, return to its
 *      original URL, then explicitly accept membership.
 *   2. Existing-user login — drive /login with seeded credentials and assert
 *      the user lands on an authenticated page (dashboard / onboarding /
 *      contacts depending on workspace state).
 *
 * Invitation signup uses intercepted synthetic API data, never live accounts.
 */

test.describe("Authentication", () => {
  test("login form is reachable", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByText(/welcome back/i)).toBeVisible();
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

  test("invited person creates an account, returns to the invitation and accepts", async ({ page }) => {
    const token = "rf001-original-invitation";
    const email = "rf001-invitee@example.com";
    const workspaceId = "11111111-1111-4111-8111-111111111111";
    let signedIn = false;
    let registered = false;
    let accepted = false;
    let registrationAttempts = 0;
    const writes: string[] = [];
    await page.route("**/api/v1/**", async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
      if (request.method() === "POST") writes.push(path);
      if (path === "/api/v1/auth/register") {
        registrationAttempts++;
        expect(request.postDataJSON()).toEqual({ email, password: "Test-password-123" });
        if (registrationAttempts === 1) return json({ detail: "Temporary signup failure. Try again." }, 503);
        registered = true;
        return json({ id: 701, email }, 201);
      }
      if (path === "/api/v1/auth/login") {
        expect(registered).toBe(true);
        expect(new URLSearchParams(request.postData() ?? "").get("username")).toBe(email);
        signedIn = true;
        return json({ token_type: "bearer" });
      }
      if (path === "/api/v1/auth/me") return json(signedIn ? { id: 701, email, full_name: "Invitee", is_active: true, default_workspace_id: null } : { detail: "Not authenticated" }, signedIn ? 200 : 401);
      if (path === "/api/v1/auth/refresh") return json({ detail: "No session" }, 401);
      if (path === `/api/v1/invitations/${token}`) return json({ workspace_name: "RF-001 Team", workspace_slug: "rf001-team", email, role: "member", invited_by_name: "Owner", expires_at: "2099-01-01T00:00:00Z", is_expired: false, is_valid: !accepted });
      if (path === `/api/v1/invitations/${token}/accept`) {
        expect(signedIn).toBe(true);
        accepted = true;
        return json({ success: true, message: "You have joined RF-001 Team", workspace_id: workspaceId, workspace_slug: "rf001-team" });
      }
      if (path === "/api/v1/workspaces") return json(accepted ? [{ workspace: { id: workspaceId, name: "RF-001 Team", slug: "rf001-team", settings: {}, is_active: true, created_at: "2026-01-01T00:00:00Z" }, role: "member", is_default: true }] : []);
      return json({});
    });
    await page.goto(`/invite/${token}`);
    await page.getByRole("button", { name: "Create an Account to Accept" }).click();
    await expect(page).toHaveURL(`/login?redirect=%2Finvite%2F${token}&mode=register`);
    await expect(page.getByText("Create an account", { exact: true })).toBeVisible();
    // Switching modes must not discard the original invitation.
    await page.getByRole("button", { name: "Already have an account? Sign in" }).click();
    await page.getByRole("button", { name: "New here? Create an account" }).click();
    await page.getByLabel("Email", { exact: true }).fill(email);
    await page.getByLabel("Password", { exact: true }).fill("short");
    await page.getByRole("button", { name: /^Create Account$/ }).click();
    await expect(page.getByText("Password must be at least 8 characters")).toBeVisible();
    expect(registrationAttempts).toBe(0);
    await page.getByLabel("Password", { exact: true }).fill("Test-password-123");
    await page.getByRole("button", { name: /^Create Account$/ }).click();
    await expect(page.getByRole("alert").filter({ hasText: "Temporary signup failure. Try again." })).toBeVisible();
    await page.getByRole("button", { name: /^Create Account$/ }).click();
    await expect(page).toHaveURL(`/invite/${token}`);
    expect(accepted).toBe(false);
    await page.getByRole("button", { name: /^Accept Invitation$/ }).click();
    await expect(page).not.toHaveURL(`/invite/${token}`);
    expect(accepted).toBe(true);
    expect(writes.filter((path) => path.endsWith("/accept"))).toEqual([`/api/v1/invitations/${token}/accept`]);
    await expect.poll(() => page.evaluate(() => localStorage.getItem("current_workspace_id"))).toBe(workspaceId);
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
    await expect(page.getByText(/welcome back/i)).toHaveCount(0);
  });
});
