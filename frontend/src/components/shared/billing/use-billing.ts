"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { navigateToBillingProvider } from "@/components/shared/billing/billing-navigation";
import { createCheckout, createPortal, getBillingStatus, type BillingStatus } from "@/lib/api/billing";
import { queryKeys } from "@/lib/query-keys";
import { getApiErrorMessage } from "@/lib/utils/errors";

/**
 * Real subscription state for the signed-in user's billing workspace. Shared by
 * the /billing page and Settings → Billing so both always agree.
 */
export function useBillingStatus() {
  return useQuery<BillingStatus>({
    queryKey: queryKeys.billing.status(),
    queryFn: getBillingStatus,
    retry: false,
  });
}

export type BillingRedirect = "checkout" | "portal";

/**
 * Checkout / customer-portal hand-off with pending state and error toasts.
 * While a redirect is in flight the matching control should be disabled.
 */
export function useBillingActions() {
  const [pending, setPending] = useState<BillingRedirect | null>(null);

  async function redirect(
    kind: BillingRedirect,
    getUrl: () => Promise<string>,
    fallback: string,
  ) {
    setPending(kind);
    try {
      navigateToBillingProvider(await getUrl());
    } catch (err) {
      toast.error(getApiErrorMessage(err, fallback));
      setPending(null);
    }
  }

  return {
    pending,
    startCheckout: () =>
      redirect(
        "checkout",
        async () => (await createCheckout()).checkout_url,
        "Failed to start checkout. Please try again.",
      ),
    openPortal: () =>
      redirect(
        "portal",
        async () => (await createPortal()).portal_url,
        "Failed to open billing portal. Please try again.",
      ),
  };
}
