import { apiGet, apiPost, apiPut, apiDelete } from "@/lib/api";
import { createApiClient, type FullApiClient } from "@/lib/api/create-api-client";
import type {
  Offer,
  DiscountType,
  GuaranteeType,
  UrgencyType,
  ValueStackItem,
} from "@/types";

// Request/Response Types
export interface OffersListParams {
  page?: number;
  page_size?: number;
  active_only?: boolean;
}

export interface OffersListResponse {
  items: Offer[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface CreateOfferRequest {
  name: string;
  description?: string | null;
  discount_type: DiscountType;
  discount_value: number;
  terms?: string | null;
  valid_from?: string | null;
  valid_until?: string | null;
  is_active?: boolean;
  // Hormozi-style fields
  headline?: string | null;
  subheadline?: string | null;
  regular_price?: number | null;
  offer_price?: number | null;
  savings_amount?: number | null;
  guarantee_type?: GuaranteeType | null;
  guarantee_days?: number | null;
  guarantee_text?: string | null;
  urgency_type?: UrgencyType | null;
  urgency_text?: string | null;
  scarcity_count?: number | null;
  value_stack_items?: ValueStackItem[] | null;
  cta_text?: string | null;
  cta_subtext?: string | null;
  lead_magnet_ids?: string[];
  // Public landing page fields
  is_public?: boolean;
  public_slug?: string | null;
  require_email?: boolean;
  require_phone?: boolean;
  require_name?: boolean;
}

export interface UpdateOfferRequest {
  // Exact attachment set, saved atomically with offer fields; [] clears all.
  lead_magnet_ids?: string[];
  name?: string;
  description?: string | null;
  discount_type?: DiscountType;
  discount_value?: number;
  terms?: string | null;
  valid_from?: string | null;
  valid_until?: string | null;
  is_active?: boolean;
  // Hormozi-style fields
  headline?: string | null;
  subheadline?: string | null;
  regular_price?: number | null;
  offer_price?: number | null;
  savings_amount?: number | null;
  guarantee_type?: GuaranteeType | null;
  guarantee_days?: number | null;
  guarantee_text?: string | null;
  urgency_type?: UrgencyType | null;
  urgency_text?: string | null;
  scarcity_count?: number | null;
  value_stack_items?: ValueStackItem[] | null;
  cta_text?: string | null;
  cta_subtext?: string | null;
  // Public landing page fields
  is_public?: boolean;
  public_slug?: string | null;
  require_email?: boolean;
  require_phone?: boolean;
  require_name?: boolean;
}

// AI Generation Types
export interface GenerateOfferRequest {
  business_type: string;
  target_audience: string;
  main_offer: string;
  price_point?: number;
  desired_outcome?: string;
  pain_points?: string[];
  unique_mechanism?: string;
}

export interface GeneratedHeadline {
  text: string;
  style?: string;
}

export interface GeneratedSubheadline {
  text: string;
}

export interface GeneratedValueStackItem {
  name: string;
  description: string;
  value: number;
}

export interface GeneratedGuarantee {
  type: string;
  days: number;
  text: string;
}

export interface GeneratedUrgency {
  type: string;
  text: string;
  count?: number;
}

export interface GeneratedCTA {
  text: string;
  subtext?: string;
}

export interface GeneratedBonusIdea {
  name: string;
  description: string;
  value: number;
  suggested_type: string;
}

export interface GeneratedOfferContent {
  success: boolean;
  error?: string;
  headlines: GeneratedHeadline[];
  subheadlines: GeneratedSubheadline[];
  value_stack_items: GeneratedValueStackItem[];
  guarantees: GeneratedGuarantee[];
  urgency_options: GeneratedUrgency[];
  ctas: GeneratedCTA[];
  bonus_ideas: GeneratedBonusIdea[];
}

const baseApi = createApiClient<Offer, CreateOfferRequest, UpdateOfferRequest>({
  resourcePath: "offers",
}) as FullApiClient<Offer, CreateOfferRequest, UpdateOfferRequest>;

// Offers API
export const offersApi = {
  ...baseApi,

  // AI Generation
  generate: async (
    workspaceId: string,
    data: GenerateOfferRequest
  ): Promise<GeneratedOfferContent> => {
    return apiPost<GeneratedOfferContent>(
      `/api/v1/workspaces/${workspaceId}/offers/generate`,
      data
    );
  },

  // Get offer with attached lead magnets
  getWithLeadMagnets: async (workspaceId: string, offerId: string): Promise<Offer> => {
    return apiGet<Offer>(
      `/api/v1/workspaces/${workspaceId}/offers/${offerId}/with-lead-magnets`
    );
  },

  // Attach lead magnets to an offer
  attachLeadMagnets: async (
    workspaceId: string,
    offerId: string,
    leadMagnetIds: string[]
  ): Promise<Offer> => {
    return apiPost<Offer>(
      `/api/v1/workspaces/${workspaceId}/offers/${offerId}/lead-magnets`,
      leadMagnetIds
    );
  },

  // Detach a lead magnet from an offer
  detachLeadMagnet: async (
    workspaceId: string,
    offerId: string,
    leadMagnetId: string
  ): Promise<void> => {
    await apiDelete(
      `/api/v1/workspaces/${workspaceId}/offers/${offerId}/lead-magnets/${leadMagnetId}`
    );
  },

  // Reorder lead magnets attached to an offer
  reorderLeadMagnets: async (
    workspaceId: string,
    offerId: string,
    leadMagnetIds: string[]
  ): Promise<Offer> => {
    return apiPut<Offer>(
      `/api/v1/workspaces/${workspaceId}/offers/${offerId}/lead-magnets/reorder`,
      leadMagnetIds
    );
  },
};
