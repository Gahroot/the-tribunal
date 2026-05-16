import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ErrorBoundary, PageErrorBoundary } from "@/components/ui/error-boundary";

function Bomb({ message = "kaboom" }: { message?: string }): React.ReactNode {
  throw new Error(message);
}

function Good() {
  return <div>all good</div>;
}

beforeEach(() => {
  // React logs the caught error to console.error — silence it for clarity.
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ErrorBoundary", () => {
  it("renders children when no error is thrown", () => {
    render(
      <ErrorBoundary>
        <Good />
      </ErrorBoundary>,
    );

    expect(screen.getByText("all good")).toBeInTheDocument();
  });

  it("renders the default fallback when a child throws", () => {
    render(
      <ErrorBoundary>
        <Bomb message="db offline" />
      </ErrorBoundary>,
    );

    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText(/db offline/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /refresh page/i })).toBeInTheDocument();
  });

  it("renders a custom fallback when provided", () => {
    render(
      <ErrorBoundary fallback={<div>custom fallback</div>}>
        <Bomb />
      </ErrorBoundary>,
    );

    expect(screen.getByText("custom fallback")).toBeInTheDocument();
    expect(screen.queryByText("Something went wrong")).not.toBeInTheDocument();
  });

  it("clears the error state when 'Try Again' is clicked", async () => {
    // Module-scoped flag the child reads on each render. Flipping it before
    // we click 'Try Again' lets the re-render succeed.
    const ref = { shouldThrow: true };
    function Conditional() {
      if (ref.shouldThrow) throw new Error("boom");
      return <Good />;
    }

    render(
      <ErrorBoundary>
        <Conditional />
      </ErrorBoundary>,
    );

    expect(screen.getByText("Something went wrong")).toBeInTheDocument();

    ref.shouldThrow = false;

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /try again/i }));

    expect(screen.getByText("all good")).toBeInTheDocument();
  });

  it("logs the caught error via componentDidCatch", () => {
    render(
      <ErrorBoundary>
        <Bomb message="logged" />
      </ErrorBoundary>,
    );

    const logged = (console.error as unknown as ReturnType<typeof vi.fn>).mock.calls
      .flat()
      .some((arg) => typeof arg === "string" && arg.includes("ErrorBoundary caught error:"));
    expect(logged).toBe(true);
  });
});

describe("PageErrorBoundary", () => {
  it("renders the page-level fallback when a child throws", () => {
    render(
      <PageErrorBoundary>
        <Bomb />
      </PageErrorBoundary>,
    );

    expect(screen.getByText("Oops! Something went wrong")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /go to dashboard/i })).toBeInTheDocument();
  });

  it("renders a custom fallback when provided", () => {
    render(
      <PageErrorBoundary fallback={<div>custom page fallback</div>}>
        <Bomb />
      </PageErrorBoundary>,
    );

    expect(screen.getByText("custom page fallback")).toBeInTheDocument();
  });

  it("renders children unchanged on the happy path", () => {
    render(
      <PageErrorBoundary>
        <Good />
      </PageErrorBoundary>,
    );

    expect(screen.getByText("all good")).toBeInTheDocument();
  });
});
