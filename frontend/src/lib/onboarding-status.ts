/**
 * Client-side persistence for the first-run onboarding gate (finding RF-002).
 *
 * One per-workspace flag lives in localStorage:
 *
 * - "card dismissed": set when the user dismisses the in-app setup card (the
 *   persistent "Finish setup" checklist). The sidebar's `setupNavItem` entry
 *   stays regardless — it opens the checklist at /onboarding — so onboarding
 *   remains discoverable after dismissal.
 *
 * The old "auto-redirected" flag was removed together with the force-redirect
 * into the wizard: first-run onboarding is now the persistent checklist card,
 * so there is no redirect left to suppress.
 */

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
    // Private mode / storage disabled: degrade to showing the card, which is
    // still better than losing onboarding entirely.
  }
}

export function isSetupCardDismissed(workspaceId: string): boolean {
  return readFlag(CARD_DISMISSED_PREFIX + workspaceId);
}

export function dismissSetupCard(workspaceId: string): void {
  writeFlag(CARD_DISMISSED_PREFIX + workspaceId);
}
