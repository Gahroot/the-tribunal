import api from "@/lib/api";
import type { ValueStackItem, LeadMagnet } from "@/types";

// Public Offer Types
export interface PublicOffer {
  name: string;
  headline?: string;
  subheadline?: string;
  description?: string;
  regular_price?: number;
  offer_price?: number;
  savings_amount?: number;
  guarantee_type?: string;
  guarantee_days?: number;
  guarantee_text?: string;
  urgency_type?: string;
  urgency_text?: string;
  scarcity_count?: number;
  value_stack_items?: ValueStackItem[];
  cta_text?: string;
  cta_subtext?: string;
  lead_magnets: LeadMagnet[];
  total_value?: number;
  require_email: boolean;
  require_phone: boolean;
  require_name: boolean;
}

export interface OptInRequest {
  email?: string;
  phone_number?: string;
  name?: string;
}

export interface OptInResponse {
  success: boolean;
  message: string;
  contact_id?: number;
  lead_magnet_lead_id?: string;
}

// Public Offers API (no auth required)
export const publicOffersApi = {
  get: async (slug: string): Promise<PublicOffer> => {
    const response = await api.get<PublicOffer>(`/api/v1/p/offers/${slug}`);
    return response.data;
  },

  optIn: async (slug: string, data: OptInRequest): Promise<OptInResponse> => {
    const response = await api.post<OptInResponse>(
      `/api/v1/p/offers/${slug}/opt-in`,
      data
    );
    return response.data;
  },
};
