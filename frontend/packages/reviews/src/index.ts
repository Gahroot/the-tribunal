// Public entry for @tribunal/reviews.
//
// Mirrors the `public_api` of docs/blocks/reviews/BLOCK.md (frontend surface).
// The block's UI is decoupled from host data internals via the reviews adapter
// (see ./adapter); the host route supplies a concrete adapter and owns chrome.

export { ReviewsPage } from "./components/reviews-page";
export { ReputationOverview } from "./components/reputation-overview";
export { ReviewsList } from "./components/reviews-list";
export { ReviewRequestsTab } from "./components/review-requests-tab";
export { SendReviewRequestDialog } from "./components/send-review-request-dialog";
export { StarRating } from "./components/star-rating";

export {
  ReviewsAdapterProvider,
  useReviewsAdapter,
  type ReviewsAdapter,
  type ReviewsApiClient,
  type ContactsSearchClient,
  type ReviewsQueryKeys,
  type ReviewsContact,
  type ReviewsListParams,
  type ReviewRequestsListParams,
  type CreateReviewRequestPayload,
  type UpdateReviewPayload,
} from "./adapter";

export type * from "./types";
