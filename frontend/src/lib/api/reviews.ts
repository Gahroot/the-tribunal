import { apiGet, apiPost, apiPut } from "@/lib/api";
import type {
  GeneratedReviewReply,
  PaginatedReviewRequests,
  PaginatedReviews,
  ReputationSummary,
  Review,
  ReviewRequestSendResult,
  ReviewSettings,
  UpdateReviewSettings,
} from "@/types/review";

export interface ReviewsListParams {
  page?: number;
  page_size?: number;
  status?: string;
  is_public?: boolean;
  sentiment?: string;
}

export interface ReviewRequestsListParams {
  page?: number;
  page_size?: number;
  status?: string;
}

export interface CreateReviewRequestPayload {
  contact_id: number;
  appointment_id?: number;
  send_now?: boolean;
}

export interface UpdateReviewPayload {
  status?: string;
  reply_draft?: string;
  reply_sent?: boolean;
}

const base = (workspaceId: string) =>
  `/api/v1/workspaces/${workspaceId}/reviews`;

export const reviewsApi = {
  // Settings
  getSettings: (workspaceId: string): Promise<ReviewSettings> =>
    apiGet<ReviewSettings>(`${base(workspaceId)}/settings`),

  updateSettings: (
    workspaceId: string,
    data: UpdateReviewSettings,
  ): Promise<ReviewSettings> =>
    apiPut<ReviewSettings>(`${base(workspaceId)}/settings`, data),

  // Reputation dashboard
  getSummary: (workspaceId: string): Promise<ReputationSummary> =>
    apiGet<ReputationSummary>(`${base(workspaceId)}/summary`),

  // Reviews
  list: (
    workspaceId: string,
    params: ReviewsListParams = {},
  ): Promise<PaginatedReviews> =>
    apiGet<PaginatedReviews>(base(workspaceId), { params }),

  get: (workspaceId: string, reviewId: string): Promise<Review> =>
    apiGet<Review>(`${base(workspaceId)}/${reviewId}`),

  update: (
    workspaceId: string,
    reviewId: string,
    data: UpdateReviewPayload,
  ): Promise<Review> =>
    apiPut<Review>(`${base(workspaceId)}/${reviewId}`, data),

  generateReply: (
    workspaceId: string,
    reviewId: string,
    tone?: string,
  ): Promise<GeneratedReviewReply> =>
    apiPost<GeneratedReviewReply>(
      `${base(workspaceId)}/${reviewId}/generate-reply`,
      tone ? { tone } : {},
    ),

  // Review requests
  listRequests: (
    workspaceId: string,
    params: ReviewRequestsListParams = {},
  ): Promise<PaginatedReviewRequests> =>
    apiGet<PaginatedReviewRequests>(`${base(workspaceId)}/requests`, {
      params,
    }),

  createRequest: (
    workspaceId: string,
    data: CreateReviewRequestPayload,
  ): Promise<ReviewRequestSendResult> =>
    apiPost<ReviewRequestSendResult>(`${base(workspaceId)}/requests`, data),
};
