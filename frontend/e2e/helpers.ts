import type { Page } from "@playwright/test";
import { expect } from "@playwright/test";

/**
 * Credentials for an existing seeded test user. Tests that require an
 * authenticated session will skip when these are not provided so that the
 * suite remains green against environments without a seeded user.
 */
export const TEST_USER = {
  email: process.env.E2E_USER_EMAIL ?? "",
  password: process.env.E2E_USER_PASSWORD ?? "",
} as const;

export function hasTestUser(): boolean {
  return TEST_USER.email.length > 0 && TEST_USER.password.length > 0;
}

/**
 * Drive the login form at /login with the seeded test credentials and wait
 * for the redirect to a workspace-scoped page. We assert on the absence of
 * the "Sign In" button rather than a specific destination URL because the
 * post-login route depends on onboarding state.
 */
export async function loginViaUI(page: Page): Promise<void> {
  if (!hasTestUser()) {
    throw new Error(
      "loginViaUI called without E2E_USER_EMAIL / E2E_USER_PASSWORD set",
    );
  }
  await page.goto("/login");
  // The login card title ("Welcome back") renders as a styled <div>, not a
  // semantic heading, so match on text rather than role.
  await expect(page.getByText(/welcome back/i)).toBeVisible();

  await page.getByLabel(/email/i).fill(TEST_USER.email);
  await page.getByLabel(/password/i).fill(TEST_USER.password);
  await page.getByRole("button", { name: /sign in/i }).click();

  // After successful login the app routes away from /login. We don't pin the
  // exact destination because workspace/onboarding state changes it.
  await expect(page).not.toHaveURL(/\/login$/, { timeout: 15_000 });
}

/**
 * Generate a unique-ish suffix for created test data so reruns don't collide
 * on unique constraints (emails, phone numbers, etc.).
 */
export function uniqueSuffix(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}
