/**
 * Extracts a human-readable error message from an unknown error value.
 *
 * Handles:
 * - Axios-style errors with `response.data.detail` (FastAPI validation errors)
 * - Standard `Error` instances
 * - Falls back to the provided `fallback` string
 */
export function getApiErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "object" && err !== null && "response" in err) {
    const axErr = err as { response?: { data?: { detail?: string } } };
    return axErr.response?.data?.detail ?? fallback;
  }
  return fallback;
}
