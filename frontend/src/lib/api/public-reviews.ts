import { apiGet, apiPost } from "@/lib/api";
import type {
  PublicFeedbackResult,
  PublicRatingResult,
  PublicReviewRequest,
} from "@/types/review";

// Public review rating-gate API (no auth required).
export const publicReviewsApi = {
  get: (token: string): Promise<PublicReviewRequest> =>
    apiGet<PublicReviewRequest>(`/api/v1/p/reviews/${token}`),

  rate: (token: string, rating: number): Promise<PublicRatingResult> =>
    apiPost<PublicRatingResult>(`/api/v1/p/reviews/${token}/rate`, {
      rating,
    }),

  submitFeedback: (
    token: string,
    body: string,
    reviewerName?: string,
  ): Promise<PublicFeedbackResult> =>
    apiPost<PublicFeedbackResult>(`/api/v1/p/reviews/${token}/feedback`, {
      body,
      reviewer_name: reviewerName,
    }),
};
