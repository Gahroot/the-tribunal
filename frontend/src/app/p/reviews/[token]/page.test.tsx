import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Suspense } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PublicReviewRequest } from "@/types/review";

import PublicReviewPage from "./page";

const { getMock, rateMock, feedbackMock } = vi.hoisted(() => ({
  getMock: vi.fn(),
  rateMock: vi.fn(),
  feedbackMock: vi.fn(),
}));

vi.mock("@/lib/api/public-reviews", () => ({
  publicReviewsApi: { get: getMock, rate: rateMock, submitFeedback: feedbackMock },
}));

const TOKEN = "tok_review";
const PUBLIC_URL = "https://g.page/r/acme/review";

function request(overrides: Partial<PublicReviewRequest> = {}): PublicReviewRequest {
  return {
    token: TOKEN,
    status: "clicked",
    rating: null,
    business_name: "Acme Realty",
    contact_first_name: "Dana",
    positive_threshold: 4,
    already_submitted: false,
    next_step: "rate",
    redirect_url: null,
    public_review_destination_missing: false,
    feedback_submitted: false,
    message: null,
    ...overrides,
  };
}

function httpError(status: number) {
  return Object.assign(new Error(`Request failed with status code ${status}`), {
    response: { status, data: { detail: "error" } },
  });
}

function resolvedParams<T>(value: T): Promise<T> {
  return Object.assign(Promise.resolve(value), { status: "fulfilled", value });
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <Suspense fallback={null}>
        <PublicReviewPage params={resolvedParams({ token: TOKEN })} />
      </Suspense>
    </QueryClientProvider>,
  );
}

describe("PublicReviewPage", () => {
  beforeEach(() => {
    getMock.mockReset();
    rateMock.mockReset();
    feedbackMock.mockReset();
  });

  it("reopened after a low rating resumes the private feedback form", async () => {
    getMock.mockResolvedValue(
      request({ status: "rated", rating: 2, already_submitted: true, next_step: "feedback" }),
    );
    renderPage();

    expect(await screen.findByText("How can we do better?")).toBeInTheDocument();
    expect(screen.queryByText(/already responded/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /public review/i })).not.toBeInTheDocument();
  });

  it("reopened after a positive rating offers the public handoff without claiming it was posted", async () => {
    getMock.mockResolvedValue(
      request({
        status: "completed",
        rating: 5,
        already_submitted: true,
        next_step: "public_review",
        redirect_url: PUBLIC_URL,
      }),
    );
    renderPage();

    const link = await screen.findByRole("link", { name: /leave a public review/i });
    expect(link).toHaveAttribute("href", PUBLIC_URL);
    expect(screen.getByText(/completely optional/i)).toBeInTheDocument();
    expect(screen.queryByText(/posted/i)).not.toBeInTheDocument();
    expect(rateMock).not.toHaveBeenCalled();
  });

  it("does not render an unsafe destination as a handoff link", async () => {
    getMock.mockResolvedValue(
      request({
        rating: 5,
        already_submitted: true,
        next_step: "public_review",
        redirect_url: "javascript:alert(1)",
      }),
    );
    renderPage();

    expect(await screen.findByText("Thank you!")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("positive rating with no destination shows an acknowledgement only", async () => {
    getMock.mockResolvedValue(
      request({
        rating: 5,
        already_submitted: true,
        next_step: "done",
        public_review_destination_missing: true,
        message: "Thanks for the great rating — your feedback has been recorded.",
      }),
    );
    renderPage();

    expect(await screen.findByText(/has been recorded/i)).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("completed feedback shows the acknowledgement without a form", async () => {
    getMock.mockResolvedValue(
      request({
        status: "completed",
        rating: 2,
        already_submitted: true,
        next_step: "done",
        feedback_submitted: true,
        message: "Thanks — we've received your feedback and will be in touch.",
      }),
    );
    renderPage();

    expect(await screen.findByText(/received your feedback/i)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /send feedback/i })).not.toBeInTheDocument();
  });

  it("invalid link shows recovery guidance and no retry loop", async () => {
    getMock.mockRejectedValue(httpError(404));
    renderPage();

    expect(await screen.findByText(/invalid or no longer active/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /try again/i })).not.toBeInTheDocument();
  });

  it("server errors offer a retry", async () => {
    getMock.mockRejectedValueOnce(httpError(503)).mockResolvedValue(request());
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: /try again/i }));
    expect(await screen.findByText("Hi Dana!")).toBeInTheDocument();
  });

  it("keeps typed feedback after a failed send and submits once on retry", async () => {
    getMock.mockResolvedValue(
      request({ status: "rated", rating: 1, already_submitted: true, next_step: "feedback" }),
    );
    feedbackMock
      .mockRejectedValueOnce(httpError(500))
      .mockResolvedValue({ success: true, message: "Thank you for your feedback." });
    renderPage();

    const textarea = await screen.findByLabelText("What went wrong?");
    expect(textarea).toHaveAttribute("maxLength", "5000");
    fireEvent.change(textarea, { target: { value: "Agent never called back" } });
    await userEvent.click(screen.getByRole("button", { name: /send feedback/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/still here/i);
    expect(textarea).toHaveValue("Agent never called back");

    await userEvent.click(screen.getByRole("button", { name: /send feedback/i }));
    expect(await screen.findByText("Thank you for your feedback.")).toBeInTheDocument();
    expect(feedbackMock).toHaveBeenCalledTimes(2);
    expect(feedbackMock).toHaveBeenLastCalledWith(TOKEN, "Agent never called back", undefined);
  });

  it("repeat feedback acknowledged by the server shows the done state", async () => {
    getMock.mockResolvedValue(
      request({ status: "rated", rating: 2, already_submitted: true, next_step: "feedback" }),
    );
    feedbackMock.mockResolvedValue({
      success: true,
      message: "We've already received your feedback — thank you.",
      already_submitted: true,
    });
    renderPage();

    fireEvent.change(await screen.findByLabelText("What went wrong?"), {
      target: { value: "Again" },
    });
    await userEvent.click(screen.getByRole("button", { name: /send feedback/i }));

    await waitFor(() =>
      expect(screen.getByText(/already received your feedback/i)).toBeInTheDocument(),
    );
    expect(screen.queryByRole("textbox", { name: /what went wrong/i })).not.toBeInTheDocument();
  });

  it("fresh low rating moves to the feedback form", async () => {
    getMock.mockResolvedValue(request());
    rateMock.mockResolvedValue({
      success: true,
      rating: 2,
      is_positive: false,
      redirect_url: null,
      public_review_destination_missing: false,
      show_feedback_form: true,
      message: "Tell us more",
    });
    renderPage();

    await userEvent.click(await screen.findByRole("button", { name: "2 stars" }));
    expect(await screen.findByText("How can we do better?")).toBeInTheDocument();
    expect(rateMock).toHaveBeenCalledWith(TOKEN, 2);
  });
});
