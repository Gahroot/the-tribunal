"use client";

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";

import { PageErrorState } from "@/components/ui/page-state";

export default function GlobalError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <html lang="en">
      <body className="bg-background">
        <PageErrorState
          className="min-h-screen"
          message={
            error.digest
              ? `An unexpected error occurred. Please try again or refresh the page. (Error ID: ${error.digest})`
              : "An unexpected error occurred. Please try again or refresh the page."
          }
          onRetry={unstable_retry}
        />
      </body>
    </html>
  );
}
