import { apiGet, apiPost } from "@/lib/api";

// ---- Types ----

export interface BillingAccount {
  id: string;
  name: string;
  kind: "workspace";
}

export interface BillingStatus {
  billing_account: BillingAccount;
  subscribed: boolean;
  plan: string | null;
  status: string | null;
  current_period_end: string | null;
  /** Stripe billing is configured on this deployment. */
  configured: boolean;
  /** A new subscription can be started via checkout. */
  checkout_available: boolean;
  /** The Stripe customer portal can be opened for this workspace. */
  portal_available: boolean;
}

// ---- API Functions ----

export function createCheckout(billingAccountId: string, priceId?: string): Promise<{ checkout_url: string }> {
  return apiPost<{ checkout_url: string }>("/api/v1/billing/checkout", {
    billing_account_id: billingAccountId,
    price_id: priceId ?? null,
  });
}

export function createPortal(billingAccountId: string): Promise<{ portal_url: string }> {
  return apiPost<{ portal_url: string }>(`/api/v1/billing/portal?billing_account_id=${encodeURIComponent(billingAccountId)}`);
}

export function getBillingAccount(billingAccountId?: string): Promise<BillingAccount> {
  const query = billingAccountId ? `?billing_account_id=${encodeURIComponent(billingAccountId)}` : "";
  return apiGet<BillingAccount>(`/api/v1/billing/account${query}`);
}

export function getBillingStatus(billingAccountId: string): Promise<BillingStatus> {
  return apiGet<BillingStatus>(`/api/v1/billing/status?billing_account_id=${encodeURIComponent(billingAccountId)}`);
}
