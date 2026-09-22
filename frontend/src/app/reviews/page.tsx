"use client";

import {
  ReviewsAdapterProvider,
  ReviewsPage,
  type ReviewsAdapter,
} from "@tribunal/reviews";

import { AppSidebar } from "@/components/layout/app-sidebar";
import { useDebounce } from "@/hooks/useDebounce";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { contactsApi } from "@/lib/api/contacts";
import { reviewsApi } from "@/lib/api/reviews";
import { queryKeys } from "@/lib/query-keys";
import { POLL_60S } from "@/lib/query-options";

// Host adapter: wires the extracted reviews block to this app's data internals
// (HTTP clients, React Query keys/options, workspace + debounce hooks). The
// package stays free of `@/lib/*` imports; this is the single injection point.
const reviewsAdapter: ReviewsAdapter = {
  useWorkspaceId,
  useDebounce,
  api: reviewsApi,
  contacts: {
    search: (workspaceId, query) =>
      contactsApi.list(workspaceId, {
        search: query || undefined,
        page_size: 20,
      }),
  },
  queryKeys: {
    all: (ws) => queryKeys.reviews.all(ws),
    summary: (ws) => queryKeys.reviews.summary(ws),
    settings: (ws) => queryKeys.reviews.settings(ws),
    list: (ws, params) =>
      queryKeys.reviews.list(ws, params as Record<string, unknown>),
    requests: (ws) => queryKeys.reviews.requests(ws),
    contactsSearch: (ws, query) => queryKeys.contacts.search(ws, query),
  },
  pollOptions: POLL_60S,
};

export default function Page() {
  return (
    <AppSidebar>
      <ReviewsAdapterProvider adapter={reviewsAdapter}>
        <ReviewsPage />
      </ReviewsAdapterProvider>
    </AppSidebar>
  );
}
