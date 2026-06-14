export type ReviewSource = "sms_request" | "google" | "facebook" | "manual";
export type ReviewSentiment = "positive" | "neutral" | "negative";
export type ReviewStatus = "new" | "replied" | "resolved" | "dismissed";
export type ReviewRequestStatus =
  | "pending"
  | "sent"
  | "clicked"
  | "rated"
  | "completed"
  | "failed";

export interface Review {
  id: string;
  workspace_id: string;
  contact_id: number | null;
  review_request_id: string | null;
  rating: number;
  body: string | null;
  reviewer_name: string | null;
  source: ReviewSource;
  sentiment: ReviewSentiment;
  status: ReviewStatus;
  is_public: boolean;
  reply_draft: string | null;
  reply_sent: boolean;
  replied_at: string | null;
  created_at: string;
  updated_at: string;
  contact_name: string | null;
}

export interface PaginatedReviews {
  items: Review[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface ReviewRequest {
  id: string;
  workspace_id: string;
  contact_id: number;
  appointment_id: number | null;
  agent_id: string | null;
  token: string;
  channel: string;
  status: ReviewRequestStatus;
  rating: number | null;
  sent_at: string | null;
  clicked_at: string | null;
  rated_at: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  contact_name: string | null;
}

export interface PaginatedReviewRequests {
  items: ReviewRequest[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface ReviewRequestSendResult {
  success: boolean;
  review_request_id: string | null;
  status: ReviewRequestStatus;
  message: string;
  detail: string | null;
}

export interface ReviewSettings {
  enabled: boolean;
  auto_request_on_completion: boolean;
  positive_threshold: number;
  google_review_url: string | null;
  facebook_review_url: string | null;
  request_message_template: string | null;
  business_name: string | null;
  request_delay_minutes: number;
  reply_tone: string | null;
}

export interface UpdateReviewSettings {
  enabled?: boolean;
  auto_request_on_completion?: boolean;
  positive_threshold?: number;
  google_review_url?: string | null;
  facebook_review_url?: string | null;
  request_message_template?: string | null;
  business_name?: string | null;
  request_delay_minutes?: number;
  reply_tone?: string | null;
}

export interface RatingBucket {
  rating: number;
  count: number;
}

export interface ReputationSummary {
  average_rating: number;
  total_reviews: number;
  public_reviews: number;
  private_feedback: number;
  new_count: number;
  reputation_score: number;
  rating_distribution: RatingBucket[];
  requests_sent: number;
  requests_rated: number;
  response_rate: number;
}

export interface GeneratedReviewReply {
  success: boolean;
  error?: string | null;
  reply?: string | null;
}

// Public rating-gate landing page
export interface PublicReviewRequest {
  token: string;
  status: ReviewRequestStatus;
  rating: number | null;
  business_name: string | null;
  contact_first_name: string | null;
  positive_threshold: number;
  already_submitted: boolean;
}

export interface PublicRatingResult {
  success: boolean;
  rating: number;
  is_positive: boolean;
  redirect_url: string | null;
  public_review_destination_missing: boolean;
  show_feedback_form: boolean;
  message: string;
}

export interface PublicFeedbackResult {
  success: boolean;
  message: string;
}
