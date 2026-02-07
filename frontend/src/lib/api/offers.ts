import api from "@/lib/api";
import type {
  Offer,
  DiscountType,
  GuaranteeType,
  UrgencyType,
  ValueStackItem,
} from "@/types";
import { createApiClient, type FullApiClient } from "@/lib/api/create-api-client";

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
  description?: string;
  discount_type: DiscountType;
  discount_value: number;
  terms?: string;
  valid_from?: string;
  valid_until?: string;
  is_active?: boolean;
  // Hormozi-style fields
  headline?: string;
  subheadline?: string;
  regular_price?: number;
  offer_price?: number;
  savings_amount?: number;
  guarantee_type?: GuaranteeType;
  guarantee_days?: number;
  guarantee_text?: string;
  urgency_type?: UrgencyType;
  urgency_text?: string;
  scarcity_count?: number;
  value_stack_items?: ValueStackItem[];
  cta_text?: string;
  cta_subtext?: string;
  lead_magnet_ids?: string[];
  // Public landing page fields
  is_public?: boolean;
  public_slug?: string;
  require_email?: boolean;
  require_phone?: boolean;
  require_name?: boolean;
}

export interface UpdateOfferRequest {
  name?: string;
  description?: string;
  discount_type?: DiscountType;
  discount_value?: number;
  terms?: string;
  valid_from?: string;
  valid_until?: string;
  is_active?: boolean;
  // Hormozi-style fields
  headline?: string;
  subheadline?: string;
  regular_price?: number;
  offer_price?: number;
  savings_amount?: number;
  guarantee_type?: GuaranteeType;
  guarantee_days?: number;
  guarantee_text?: string;
  urgency_type?: UrgencyType;
  urgency_text?: string;
  scarcity_count?: number;
  value_stack_items?: ValueStackItem[];
  cta_text?: string;
  cta_subtext?: string;
  // Public landing page fields
  is_public?: boolean;
  public_slug?: string;
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
    const response = await api.post<GeneratedOfferContent>(
      `/api/v1/workspaces/${workspaceId}/offers/generate`,
      data
    );
    return response.data;
  },

  // Get offer with attached lead magnets
  getWithLeadMagnets: async (workspaceId: string, offerId: string): Promise<Offer> => {
    const response = await api.get<Offer>(
      `/api/v1/workspaces/${workspaceId}/offers/${offerId}/with-lead-magnets`
    );
    return response.data;
  },

  // Attach lead magnets to an offer
  attachLeadMagnets: async (
    workspaceId: string,
    offerId: string,
    leadMagnetIds: string[]
  ): Promise<Offer> => {
    const response = await api.post<Offer>(
      `/api/v1/workspaces/${workspaceId}/offers/${offerId}/lead-magnets`,
      leadMagnetIds
    );
    return response.data;
  },

  // Detach a lead magnet from an offer
  detachLeadMagnet: async (
    workspaceId: string,
    offerId: string,
    leadMagnetId: string
  ): Promise<void> => {
    await api.delete(
      `/api/v1/workspaces/${workspaceId}/offers/${offerId}/lead-magnets/${leadMagnetId}`
    );
  },

  // Reorder lead magnets attached to an offer
  reorderLeadMagnets: async (
    workspaceId: string,
    offerId: string,
    leadMagnetIds: string[]
  ): Promise<Offer> => {
    const response = await api.put<Offer>(
      `/api/v1/workspaces/${workspaceId}/offers/${offerId}/lead-magnets/reorder`,
      leadMagnetIds
    );
    return response.data;
  },
};
