/**
 * Client-side persistence for the first-run onboarding gate (finding RF-002).
 *
 * Two independent, per-workspace flags live in localStorage:
 *
 * - "auto-redirected": set once we have force-redirected a brand-new workspace
 *   to /onboarding (or the user has landed there themselves / explicitly
 *   skipped). Gating the automatic redirect on this flag means a user who skips
 *   setup is never trapped in a redirect loop — they only get sent there once.
 * - "card dismissed": set when the user dismisses the in-app setup card. The
 *   persistent "Finish setup" sidebar entry stays regardless, so onboarding
 *   remains discoverable after dismissal.
 */

const AUTO_REDIRECT_PREFIX = "onboarding_autoredirected:";
const CARD_DISMISSED_PREFIX = "onboarding_card_dismissed:";

function readFlag(key: string): boolean {
  if (typeof window === "undefined") return false;
  try {
    return localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function writeFlag(key: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(key, "1");
  } catch {
    // Private mode / storage disabled: degrade to redirecting every landing,
    // which is still better than never guiding a fresh workspace to setup.
  }
}

export function hasAutoRedirectedToOnboarding(workspaceId: string): boolean {
  return readFlag(AUTO_REDIRECT_PREFIX + workspaceId);
}

export function markAutoRedirectedToOnboarding(workspaceId: string): void {
  writeFlag(AUTO_REDIRECT_PREFIX + workspaceId);
}

export function isSetupCardDismissed(workspaceId: string): boolean {
  return readFlag(CARD_DISMISSED_PREFIX + workspaceId);
}

export function dismissSetupCard(workspaceId: string): void {
  writeFlag(CARD_DISMISSED_PREFIX + workspaceId);
}
