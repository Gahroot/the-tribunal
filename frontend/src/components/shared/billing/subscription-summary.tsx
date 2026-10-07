"use client";

import { CreditCard, Loader2 } from "lucide-react";
import Link from "next/link";

import { useBillingActions, useBillingStatus } from "@/components/shared/billing/use-billing";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { getApiErrorMessage } from "@/lib/utils/errors";

const STATUS_LABELS: Record<string, { label: string; dot: string }> = {
  active: { label: "Active", dot: "bg-success" },
  trialing: { label: "Trial", dot: "bg-info" },
  past_due: { label: "Past due", dot: "bg-warning" },
  unpaid: { label: "Unpaid", dot: "bg-destructive" },
  incomplete: { label: "Incomplete", dot: "bg-warning" },
  paused: { label: "Paused", dot: "bg-warning" },
  canceled: { label: "Canceled", dot: "bg-muted-foreground" },
  incomplete_expired: { label: "Expired", dot: "bg-muted-foreground" },
};

/** Statuses where a subscription still exists and must be fixed, not replaced. */
const NEEDS_ATTENTION = new Set(["past_due", "unpaid", "incomplete", "paused"]);

function planLabel(plan: string | null): string {
  // Stripe returns a bare product id ("prod_…") when the price has no nickname.
  return plan && !plan.startsWith("prod_") ? plan : "Monthly subscription";
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export interface SubscriptionSummaryProps {
  /**
   * How to offer a new subscription. `checkout` starts Stripe Checkout
   * directly (use only where the price is shown); `billing-page` hands off to
   * /billing so the operator sees the plan and price first.
   */
  subscribeMode: "checkout" | "billing-page";
}

/**
 * Current subscription state plus the billing actions that can actually work
 * right now. Renders honest loading / error / not-configured states instead of
 * controls that would fail.
 */
export function SubscriptionSummary({ subscribeMode }: SubscriptionSummaryProps) {
  const { data, isPending, isError, error, refetch, isFetching } = useBillingStatus();
  const { pending, startCheckout, openPortal } = useBillingActions();

  if (isPending) {
    return (
      <div role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" aria-hidden="true" />
        Loading billing status…
      </div>
    );
  }

  if (isError) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Couldn&apos;t load billing status</AlertTitle>
        <AlertDescription className="space-y-3">
          <p>
            {getApiErrorMessage(error, "Something went wrong while checking your subscription.")}{" "}
            Your subscription hasn&apos;t changed.
          </p>
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            Try again
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  if (!data.configured) {
    return (
      <Alert>
        <AlertTitle>Billing isn&apos;t set up yet</AlertTitle>
        <AlertDescription className="space-y-3">
          <p>
            Online payments haven&apos;t been configured for this account, so subscriptions
            can&apos;t be started or managed here. Ask your administrator to finish billing
            setup, then check again.
          </p>
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            Check again
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  const portalButton = (label: string) =>
    data.portal_available ? (
      <Button variant="outline" onClick={openPortal} disabled={pending !== null}>
        {pending === "portal" ? (
          <Loader2 className="mr-2 size-4 animate-spin" aria-hidden="true" />
        ) : (
          <CreditCard className="mr-2 size-4" aria-hidden="true" />
        )}
        {label}
      </Button>
    ) : null;

  const statusMeta = data.status ? STATUS_LABELS[data.status] : undefined;

  if (data.subscribed) {
    return (
      <div className="space-y-4">
        <SummaryRow
          title={planLabel(data.plan)}
          status={statusMeta ?? { label: "Active", dot: "bg-success" }}
          detail={
            data.status === "trialing" && data.current_period_end
              ? `Trial ends ${formatDate(data.current_period_end)}`
              : "Use Manage subscription to review or change your billing in Stripe."
          }
        />
        <div className="flex flex-wrap gap-2">{portalButton("Manage subscription")}</div>
      </div>
    );
  }

  if (data.status && NEEDS_ATTENTION.has(data.status)) {
    return (
      <div className="space-y-4">
        <SummaryRow
          title={planLabel(data.plan)}
          status={statusMeta ?? { label: data.status, dot: "bg-warning" }}
          detail={
            data.portal_available
              ? "Your subscription needs attention. Update your payment details in the billing portal to restore access."
              : "Your subscription needs attention. Contact support to restore access."
          }
        />
        <div className="flex flex-wrap gap-2">{portalButton("Update payment details")}</div>
      </div>
    );
  }

  const subscribeControl = !data.checkout_available ? null : subscribeMode === "checkout" ? (
    <Button size="lg" className="w-full" onClick={startCheckout} disabled={pending !== null}>
      {pending === "checkout" ? (
        <Loader2 className="mr-2 size-4 animate-spin" aria-hidden="true" />
      ) : (
        <CreditCard className="mr-2 size-4" aria-hidden="true" />
      )}
      Get Started
    </Button>
  ) : (
    <Button asChild>
      <Link href="/billing">View plan and subscribe</Link>
    </Button>
  );

  return (
    <div className="space-y-4">
      <SummaryRow
        title="No active subscription"
        status={statusMeta}
        detail={
          data.checkout_available
            ? data.status
              ? "Your previous subscription has ended. Subscribe again to keep AI follow-up running."
              : "Subscribe to turn on AI follow-up for your leads."
            : "New subscriptions aren't available right now because no plan is configured. Contact support to subscribe."
        }
      />
      <div className="flex flex-wrap gap-2">
        {subscribeControl}
        {portalButton("Open billing portal")}
      </div>
    </div>
  );
}

function SummaryRow({
  title,
  status,
  detail,
}: {
  title: string;
  status?: { label: string; dot: string };
  detail: string;
}) {
  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="font-semibold">{title}</h3>
        {status ? <StatusBadge dotClass={status.dot}>{status.label}</StatusBadge> : null}
      </div>
      <p className="mt-1 text-sm text-muted-foreground">{detail}</p>
    </div>
  );
}

