"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { StarRating } from "@tribunal/reviews";
import { CheckCircle2, ExternalLink, Loader2, Star } from "lucide-react";
import { type ReactNode, use, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { PageErrorState, PageLoadingState } from "@/components/ui/page-state";
import { Textarea } from "@/components/ui/textarea";
import { publicReviewsApi } from "@/lib/api/public-reviews";
import { queryKeys } from "@/lib/query-keys";
import type {
  PublicRatingResult,
  PublicReviewNextStep,
  PublicReviewRequest,
} from "@/types/review";

// Mirrors the backend PublicFeedbackSubmit limits.
const FEEDBACK_MAX_LENGTH = 5000;
const NAME_MAX_LENGTH = 255;

const INVALID_LINK_MESSAGE =
  "This review link is invalid or no longer active. If it came from a text message, ask the business to send you a new link.";

interface PublicReviewPageProps {
  params: Promise<{ token: string }>;
}

/** What the page shows, resumed from the server or set by this visit. */
interface Step {
  step: PublicReviewNextStep;
  rating: number;
  redirectUrl: string | null;
  feedbackSubmitted: boolean;
  message: string | null;
}

function getHttpStatus(err: unknown): number | null {
  if (typeof err !== "object" || err === null) return null;
  const status = (err as { response?: { status?: unknown } }).response?.status;
  return typeof status === "number" ? status : null;
}

/** Only hand off to real web pages; anything else is treated as missing. */
function safeHttpUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:"
      ? parsed.toString()
      : null;
  } catch {
    return null;
  }
}

function stepFromRequest(data: PublicReviewRequest): Step {
  const redirectUrl = safeHttpUrl(data.redirect_url);
  let step: PublicReviewNextStep =
    data.next_step ?? (data.already_submitted ? "done" : "rate");
  if (step === "public_review" && !redirectUrl) step = "done";
  return {
    step,
    rating: data.rating ?? 0,
    redirectUrl,
    feedbackSubmitted: !!data.feedback_submitted,
    message: data.message ?? null,
  };
}

function stepFromRating(result: PublicRatingResult): Step {
  const redirectUrl = safeHttpUrl(result.redirect_url);
  let step: PublicReviewNextStep = "done";
  if (result.show_feedback_form) step = "feedback";
  else if (result.is_positive && redirectUrl) step = "public_review";
  return {
    step,
    rating: result.rating,
    redirectUrl,
    feedbackSubmitted: !!result.feedback_submitted,
    message: result.message,
  };
}

function FullPage({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-gradient-to-br from-background to-muted">
      {children}
    </div>
  );
}

export default function PublicReviewPage({ params }: PublicReviewPageProps) {
  const { token } = use(params);

  const [selectedRating, setSelectedRating] = useState(0);
  const [localStep, setLocalStep] = useState<Step | null>(null);
  const [feedback, setFeedback] = useState("");
  const [feedbackName, setFeedbackName] = useState("");

  const { data, isPending, error, refetch, isRefetching } = useQuery({
    queryKey: queryKeys.publicReviews.byToken(token),
    queryFn: () => publicReviewsApi.get(token),
    enabled: !!token,
    retry: false,
  });

  const rateMutation = useMutation({
    mutationFn: (rating: number) => publicReviewsApi.rate(token, rating),
    onSuccess: (result) => {
      const next = stepFromRating(result);
      setLocalStep(next);
      // A fresh positive rating hands off to the configured public site. The
      // handoff link stays on screen in case the redirect is blocked.
      if (next.step === "public_review" && next.redirectUrl) {
        window.location.assign(next.redirectUrl);
      }
    },
  });

  const feedbackMutation = useMutation({
    mutationFn: () =>
      publicReviewsApi.submitFeedback(
        token,
        feedback.trim(),
        feedbackName.trim() || undefined,
      ),
    onSuccess: (result) =>
      setLocalStep((prev) => ({
        step: "done",
        rating: prev?.rating ?? data?.rating ?? 0,
        redirectUrl: null,
        feedbackSubmitted: true,
        message: result.message,
      })),
  });

  if (isPending) {
    return (
      <FullPage>
        <PageLoadingState className="min-h-screen" />
      </FullPage>
    );
  }

  if (error || !data) {
    const notFound = getHttpStatus(error) === 404;
    return (
      <FullPage>
        <PageErrorState
          className="min-h-screen"
          message={
            notFound
              ? INVALID_LINK_MESSAGE
              : "We couldn't load this page right now. Please check your connection and try again."
          }
          onRetry={notFound || isRefetching ? undefined : () => void refetch()}
        />
      </FullPage>
    );
  }

  const feedbackStatus = getHttpStatus(feedbackMutation.error);
  if (getHttpStatus(rateMutation.error) === 404 || feedbackStatus === 404) {
    return (
      <FullPage>
        <PageErrorState className="min-h-screen" message={INVALID_LINK_MESSAGE} />
      </FullPage>
    );
  }

  const businessName = data.business_name || "us";
  const current = localStep ?? stepFromRequest(data);
  const displayRating = selectedRating || current.rating;

  const handleSelect = (rating: number) => {
    if (rateMutation.isPending) return;
    setSelectedRating(rating);
    rateMutation.mutate(rating);
  };

  const feedbackTooLong = feedback.length > FEEDBACK_MAX_LENGTH;

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-background to-muted p-4">
      <Card className="max-w-md w-full">
        {current.step === "done" ? (
          <CardContent className="pt-6 text-center space-y-3">
            <CheckCircle2 className="size-16 text-success mx-auto" />
            <h1 className="text-2xl font-bold">Thank you!</h1>
            <p className="text-muted-foreground">
              {current.message ??
                (current.feedbackSubmitted
                  ? "We've received your feedback and will be in touch."
                  : "Thanks for letting us know how we did.")}
            </p>
          </CardContent>
        ) : current.step === "public_review" && current.redirectUrl ? (
          <>
            <CardHeader className="text-center">
              <CheckCircle2 className="size-12 text-success mx-auto" />
              <CardTitle className="mt-2">Thanks for your rating!</CardTitle>
              <p className="text-sm text-muted-foreground">
                If you&apos;d like, you can also share your experience with{" "}
                {businessName} publicly.
              </p>
            </CardHeader>
            <CardContent className="space-y-4">
              {displayRating > 0 && (
                <div className="flex justify-center">
                  <StarRating value={displayRating} size="md" />
                </div>
              )}
              <Button asChild className="w-full">
                <a href={current.redirectUrl} rel="noopener noreferrer">
                  Leave a public review
                  <ExternalLink className="size-4" />
                </a>
              </Button>
              <p className="text-center text-xs text-muted-foreground">
                You&apos;ll be taken to the review site. Sharing is completely
                optional.
              </p>
            </CardContent>
          </>
        ) : current.step === "feedback" ? (
          <>
            <CardHeader className="text-center">
              <CardTitle>How can we do better?</CardTitle>
              <p className="text-sm text-muted-foreground">
                Your feedback goes straight to the {businessName} team, not a
                public page.
              </p>
            </CardHeader>
            <CardContent className="space-y-4">
              {displayRating > 0 && (
                <div className="flex justify-center">
                  <StarRating value={displayRating} size="md" />
                </div>
              )}
              <div className="space-y-2">
                <Label htmlFor="name">Your name (optional)</Label>
                <input
                  id="name"
                  className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm"
                  value={feedbackName}
                  maxLength={NAME_MAX_LENGTH}
                  onChange={(e) => setFeedbackName(e.target.value)}
                  placeholder="Jane Doe"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="feedback">What went wrong?</Label>
                <Textarea
                  id="feedback"
                  rows={4}
                  value={feedback}
                  maxLength={FEEDBACK_MAX_LENGTH}
                  aria-describedby="feedback-count"
                  onChange={(e) => setFeedback(e.target.value)}
                  placeholder="Tell us what happened so we can make it right…"
                />
                <p
                  id="feedback-count"
                  className={
                    feedbackTooLong
                      ? "text-right text-xs text-destructive"
                      : "text-right text-xs text-muted-foreground"
                  }
                >
                  {feedback.length} / {FEEDBACK_MAX_LENGTH} characters
                </p>
              </div>
              {feedbackMutation.isError && (
                <p role="alert" className="text-center text-sm text-destructive">
                  {feedbackStatus === 422
                    ? `Please keep your feedback under ${FEEDBACK_MAX_LENGTH} characters and try again.`
                    : "We couldn't send your feedback. Your message is still here — please try again."}
                </p>
              )}
              <Button
                className="w-full"
                onClick={() => feedbackMutation.mutate()}
                disabled={
                  feedback.trim().length === 0 ||
                  feedbackTooLong ||
                  feedbackMutation.isPending
                }
              >
                {feedbackMutation.isPending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  "Send feedback"
                )}
              </Button>
            </CardContent>
          </>
        ) : (
          <>
            <CardHeader className="text-center">
              <Star className="size-10 text-warning mx-auto fill-warning" />
              <CardTitle className="mt-2">
                {data.contact_first_name
                  ? `Hi ${data.contact_first_name}!`
                  : "How did we do?"}
              </CardTitle>
              <p className="text-sm text-muted-foreground">
                Rate your experience with {businessName}.
              </p>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex justify-center py-4">
                <StarRating
                  value={selectedRating}
                  size="lg"
                  onChange={handleSelect}
                />
              </div>
              {rateMutation.isPending && (
                <div className="flex justify-center">
                  <Loader2 className="size-5 animate-spin text-muted-foreground" />
                </div>
              )}
              {rateMutation.isError && (
                <p role="alert" className="text-center text-sm text-destructive">
                  We couldn&apos;t save your rating. Please tap a star to try
                  again.
                </p>
              )}
            </CardContent>
          </>
        )}
      </Card>
    </div>
  );
}
