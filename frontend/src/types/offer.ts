// Offer Types

import type { LeadMagnet } from "./lead-magnet";

export type DiscountType = "percentage" | "fixed" | "free_service";
export type GuaranteeType = "money_back" | "satisfaction" | "results";
export type UrgencyType = "limited_time" | "limited_quantity" | "expiring";

export interface ValueStackItem {
  name: string;
  description?: string;
  value: number;
  included: boolean;
}

export interface Offer {
  id: string;
  workspace_id: string;
  name: string;
  description?: string;
  discount_type: DiscountType;
  discount_value: number;
  terms?: string;
  valid_from?: string;
  valid_until?: string;
  is_active: boolean;
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
  page_views?: number;
  opt_ins?: number;
  // Computed fields
  lead_magnets?: LeadMagnet[];
  total_value?: number;
  created_at: string;
  updated_at: string;
}

export interface OfferLeadMagnet {
  id: string;
  offer_id: string;
  lead_magnet_id: string;
  sort_order: number;
  is_bonus: boolean;
  created_at: string;
  lead_magnet: LeadMagnet;
}
