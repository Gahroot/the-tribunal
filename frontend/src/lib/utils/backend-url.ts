/**
 * Centralized accessors for the backend URL.
 *
 * `NEXT_PUBLIC_API_URL` is read here in one place so callsites never have to
 * juggle defaults or sanitize the env var. Trimming guards against accidental
 * trailing whitespace/newlines pasted into deployment env editors.
 */

const DEFAULT_BACKEND_URL = "http://localhost:8000";

/**
 * Returns the configured backend HTTP origin (e.g. `https://api.example.com`).
 *
 * Note: in the browser, prefer empty-string baseURL so requests flow through
 * the Next.js rewrite proxy (avoids CORS). This helper returns the *direct*
 * origin and is intended for SSR/Node contexts or for deriving the WS URL.
 */
export function getBackendUrl(): string {
  return (process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_BACKEND_URL).trim();
}

/**
 * Returns the backend WebSocket origin, derived from {@link getBackendUrl}.
 * Converts `http://` → `ws://` and `https://` → `wss://`.
 */
export function getBackendWsUrl(): string {
  const httpUrl = getBackendUrl();
  if (httpUrl.startsWith("https://")) return `wss://${httpUrl.slice("https://".length)}`;
  if (httpUrl.startsWith("http://")) return `ws://${httpUrl.slice("http://".length)}`;
  // No scheme — fall back to ws:// for local/dev hostnames.
  return `ws://${httpUrl}`;
}
