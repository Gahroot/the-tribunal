"use client";

import { QueryErrorResetBoundary } from "@tanstack/react-query";
import { Component, type ErrorInfo, type ReactNode } from "react";

import { PageErrorState } from "@/components/ui/page-state";

interface ResettableBoundaryProps {
  children: ReactNode;
  /** Clears any React Query errors captured inside this boundary on retry. */
  onReset: () => void;
  message: string;
}

interface ResettableBoundaryState {
  hasError: boolean;
}

/**
 * Class boundary that catches render-time throws (including React Query's
 * `throwOnError` propagation) and shows an inline, retryable fallback instead
 * of letting the error bubble to the route-level `error.tsx`.
 */
class ResettableErrorBoundary extends Component<
  ResettableBoundaryProps,
  ResettableBoundaryState
> {
  state: ResettableBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ResettableBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    if (process.env.NODE_ENV !== "production") {
      console.error("QueryErrorBoundary caught error:", error, errorInfo);
    }
  }

  handleRetry = (): void => {
    // Clear the cached query error first so the children refetch instead of
    // immediately re-throwing the stale error, then re-render the subtree.
    this.props.onReset();
    this.setState({ hasError: false });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return <PageErrorState message={this.props.message} onRetry={this.handleRetry} />;
    }
    return this.props.children;
  }
}

export interface QueryErrorBoundaryProps {
  children: ReactNode;
  /** Inline message shown when a query inside this boundary fails. */
  message?: string;
}

/**
 * Contains data-fetching failures to a local region. Wrap an independent
 * section (e.g. a single settings tab) so one failing request renders a
 * retryable inline state here instead of replacing the whole page via the
 * nearest route `error.tsx` boundary.
 */
export function QueryErrorBoundary({
  children,
  message = "Failed to load this section. Please try again.",
}: QueryErrorBoundaryProps) {
  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <ResettableErrorBoundary onReset={reset} message={message}>
          {children}
        </ResettableErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  );
}
