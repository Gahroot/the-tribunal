/**
 * Post-sign-in return destinations (finding RF-003).
 *
 * A return destination arrives through an untrusted query string
 * (`/login?redirect=...`), so it must never be able to send the browser to
 * another origin. Only same-origin, in-app paths are permitted; anything else
 * is rejected and callers fall back to the dashboard.
 *
 * Safe to import from both server and client components.
 */

export const RETURN_TO_PARAM = "redirect";

const MAX_RETURN_TO_LENGTH = 2048;

// Sentinel origin used only to resolve the candidate path. If resolution lands
// anywhere else (protocol-relative `//host`, `/\host`, `javascript:` ...), the
// value was not a local path.
const LOCAL_ORIGIN = "http://return-to.invalid";

// Paths that must never be a post-sign-in destination: the auth pages
// themselves (would loop) and raw API routes (not pages).
const BLOCKED_PATHS = ["/login", "/register", "/api"];

function hasControlCharacter(value: string): boolean {
  for (let i = 0; i < value.length; i += 1) {
    const code = value.charCodeAt(i);
    if (code <= 0x1f || code === 0x7f) return true;
  }
  return false;
}

/**
 * Return a normalized local path (`/path?query#hash`) when `value` is a
 * permitted in-app destination, otherwise `null`.
 */
export function getSafeReturnTo(value: unknown): string | null {
  if (typeof value !== "string") return null;
  if (value.length === 0 || value.length > MAX_RETURN_TO_LENGTH) return null;
  // Must be a single-slash rooted path: rejects absolute URLs, scheme URLs,
  // protocol-relative `//host`, and backslash variants browsers treat as `/`.
  if (!value.startsWith("/") || value.startsWith("//")) return null;
  if (value.includes("\\") || hasControlCharacter(value)) return null;

  let url: URL;
  try {
    url = new URL(value, LOCAL_ORIGIN);
  } catch {
    return null;
  }
  if (url.origin !== LOCAL_ORIGIN) return null;

  const { pathname } = url;
  if (BLOCKED_PATHS.some((blocked) => pathname === blocked || pathname.startsWith(`${blocked}/`))) {
    return null;
  }

  return `${pathname}${url.search}${url.hash}`;
}

/** Build the sign-in URL, carrying `returnTo` only when it is permitted. */
export function buildLoginHref(returnTo?: string | null): string {
  const safe = getSafeReturnTo(returnTo);
  return safe ? `/login?${RETURN_TO_PARAM}=${encodeURIComponent(safe)}` : "/login";
}

/** Path of the public invitation page for `token`. */
export function invitePath(token: string): string {
  return `/invite/${encodeURIComponent(token)}`;
}
