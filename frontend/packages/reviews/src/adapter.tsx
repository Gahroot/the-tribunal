"use client";

// Data-layer adapter for the reviews block.
//
// The block's UI is decoupled from the host app's data internals (HTTP client,
// React Query keys/options, workspace + debounce hooks). The host supplies a
// concrete `ReviewsAdapter` through `ReviewsAdapterProvider`; components read it
// via `useReviewsAdapter()`. This is what lets the package render in any app
// without hard-importing `@/lib/api/*`, `@/lib/query-keys`, `@/lib/query-options`
// or `@/hooks/*`.

import { createContext, useContext, type ReactNode } from "react";

import type {
  GeneratedReviewReply,
  PaginatedReviewRequests,
  PaginatedReviews,
  ReputationSummary,
  Review,
  ReviewRequestSendResult,
  ReviewSettings,
  UpdateReviewSettings,
} from "./types";

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

/** Minimal contact shape the send-request dialog needs (structurally compatible
 * with the host's richer `Contact`). */
export interface ReviewsContact {
  id: number;
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  phone_number?: string | null;
}

export interface ReviewsApiClient {
  getSettings(workspaceId: string): Promise<ReviewSettings>;
  updateSettings(
    workspaceId: string,
    data: UpdateReviewSettings,
  ): Promise<ReviewSettings>;
  getSummary(workspaceId: string): Promise<ReputationSummary>;
  list(workspaceId: string, params?: ReviewsListParams): Promise<PaginatedReviews>;
  get(workspaceId: string, reviewId: string): Promise<Review>;
  update(
    workspaceId: string,
    reviewId: string,
    data: UpdateReviewPayload,
  ): Promise<Review>;
  generateReply(
    workspaceId: string,
    reviewId: string,
    tone?: string,
  ): Promise<GeneratedReviewReply>;
  listRequests(
    workspaceId: string,
    params?: ReviewRequestsListParams,
  ): Promise<PaginatedReviewRequests>;
  createRequest(
    workspaceId: string,
    data: CreateReviewRequestPayload,
  ): Promise<ReviewRequestSendResult>;
}

export interface ContactsSearchClient {
  search(
    workspaceId: string,
    query: string,
  ): Promise<{ items: ReviewsContact[] }>;
}

/** React Query keys the block reads — injected so the package shares the host's
 * cache namespace instead of inventing its own. */
export interface ReviewsQueryKeys {
  all(workspaceId: string): readonly unknown[];
  summary(workspaceId: string): readonly unknown[];
  settings(workspaceId: string): readonly unknown[];
  list(workspaceId: string, params: ReviewsListParams): readonly unknown[];
  requests(workspaceId: string): readonly unknown[];
  contactsSearch(workspaceId: string, query: string): readonly unknown[];
}

export interface ReviewsAdapter {
  /** Resolve the active workspace id (host hook). */
  useWorkspaceId(): string | null;
  /** Debounce a changing value (host hook). */
  useDebounce<T>(value: T, delayMs: number): T;
  api: ReviewsApiClient;
  contacts: ContactsSearchClient;
  queryKeys: ReviewsQueryKeys;
  /** React Query polling preset (e.g. the host's `POLL_60S`). */
  pollOptions: Record<string, unknown>;
}

const ReviewsAdapterContext = createContext<ReviewsAdapter | null>(null);

export function ReviewsAdapterProvider({
  adapter,
  children,
}: {
  adapter: ReviewsAdapter;
  children: ReactNode;
}) {
  return (
    <ReviewsAdapterContext.Provider value={adapter}>
      {children}
    </ReviewsAdapterContext.Provider>
  );
}

export function useReviewsAdapter(): ReviewsAdapter {
  const adapter = useContext(ReviewsAdapterContext);
  if (!adapter) {
    throw new Error(
      "useReviewsAdapter must be used within a <ReviewsAdapterProvider>. " +
        "Wrap the reviews UI with the host adapter (see frontend/src/app/reviews).",
    );
  }
  return adapter;
}
