"use client";

import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { navigateToBillingProvider } from "@/components/shared/billing/billing-navigation";
import { createCheckout, createPortal, getBillingAccount, getBillingStatus, type BillingStatus } from "@/lib/api/billing";
import { queryKeys } from "@/lib/query-keys";
import { getApiErrorMessage } from "@/lib/utils/errors";
import { useAuth } from "@/providers/auth-provider";

/**
 * Real subscription state for the signed-in user's billing workspace. Shared by
 * the /billing page and Settings → Billing so both always agree.
 */
export function useBillingStatus() {
  const { user } = useAuth();
  // Stripe returns pin the account even if defaults changed during the hand-off.
  const requestedId = useSearchParams().get("billing_account_id") ?? undefined;
  const account = useQuery({
    queryKey: queryKeys.billing.account(user?.id ?? "signed-out", requestedId),
    queryFn: () => getBillingAccount(requestedId),
    enabled: !!user,
    retry: false,
  });
  const status = useQuery<BillingStatus>({
    queryKey: queryKeys.billing.status(user?.id ?? "signed-out", account.data?.id),
    queryFn: () => getBillingStatus(account.data!.id),
    enabled: !!user && !!account.data && !account.isError,
    retry: false,
  });
  return {
    ...status,
    data: account.isError || status.isError ? undefined : status.data,
    isPending: !account.isError && (account.isPending || status.isPending),
    isError: account.isError || status.isError,
    error: account.error ?? status.error,
    isFetching: account.isFetching || status.isFetching,
    refetch: account.isError ? account.refetch : status.refetch,
  };
}

export type BillingRedirect = "checkout" | "portal";

/**
 * Checkout / customer-portal hand-off with pending state and error toasts.
 * While a redirect is in flight the matching control should be disabled.
 */
export function useBillingActions(billingAccountId?: string) {
  const [pending, setPending] = useState<BillingRedirect | null>(null);

  async function redirect(
    kind: BillingRedirect,
    getUrl: () => Promise<string>,
    fallback: string,
  ) {
    if (!billingAccountId) return;
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
        async () => (await createCheckout(billingAccountId!)).checkout_url,
        "Failed to start checkout. Please try again.",
      ),
    openPortal: () =>
      redirect(
        "portal",
        async () => (await createPortal(billingAccountId!)).portal_url,
        "Failed to open billing portal. Please try again.",
      ),
  };
}
