"use client";

import { useEffect } from "react";

/**
 * Structured error reporter. Logs error details in a consistent format.
 * TODO: Replace with Sentry.captureException() or similar when error
 * monitoring is set up.
 */
function reportError(
  error: Error & { digest?: string },
  context?: { componentStack?: string },
) {
  console.error("[ErrorBoundary]", {
    message: error.message,
    digest: error.digest,
    stack: error.stack,
    componentStack: context?.componentStack,
    timestamp: new Date().toISOString(),
  });
}

export default function Error({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    reportError(error);
  }, [error]);

  return (
    <div className="flex min-h-[400px] items-center justify-center">
      <div className="flex flex-col items-center gap-4 text-center p-8">
        <h2 className="text-2xl font-semibold">Something went wrong</h2>
        <p className="text-muted-foreground max-w-md">
          An unexpected error occurred. Please try again or refresh the page.
        </p>
        {error.digest && (
          <p className="text-xs text-muted-foreground">Error ID: {error.digest}</p>
        )}
        <button
          onClick={unstable_retry}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
