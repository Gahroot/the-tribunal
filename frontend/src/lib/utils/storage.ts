// Shared localStorage utility with SSR guard and error handling.
//
// NOTE: Auth tokens are NOT stored here. The access_token and refresh_token
// are both httpOnly cookies set by the backend (see backend/app/api/v1/auth.py)
// — JS cannot read them, so an XSS payload cannot exfiltrate them. Use these
// helpers only for non-sensitive UI state (theme, last-viewed tab, etc.).

export function safeGetItem(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(key);
  } catch (error) {
    console.warn(`Failed to access localStorage for key "${key}":`, error);
    return null;
  }
}

export function safeSetItem(key: string, value: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(key, value);
  } catch (error) {
    console.warn(`Failed to set localStorage key "${key}":`, error);
  }
}

export function safeRemoveItem(key: string): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(key);
  } catch (error) {
    console.warn(`Failed to remove localStorage key "${key}":`, error);
  }
}
