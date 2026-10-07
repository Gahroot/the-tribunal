/**
 * Send the browser to a Stripe-hosted billing page (Checkout or the customer
 * portal). Kept in its own module so tests can observe the hand-off without
 * jsdom attempting a real navigation.
 *
 * Only absolute https URLs are followed; anything else (empty string, relative
 * path, javascript: URL) is rejected so a bad backend response can't turn into
 * a dead click or an unsafe redirect.
 */
export function navigateToBillingProvider(url: string): void {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new Error("The billing provider didn't return a valid link. Please try again.");
  }
  if (parsed.protocol !== "https:") {
    throw new Error("The billing provider didn't return a secure link. Please try again.");
  }
  window.location.assign(parsed.toString());
}
