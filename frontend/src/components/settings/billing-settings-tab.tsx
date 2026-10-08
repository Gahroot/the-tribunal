"use client";

import Link from "next/link";

import { SubscriptionSummary } from "@/components/shared/billing/subscription-summary";
import { useBillingStatus } from "@/components/shared/billing/use-billing";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

/**
 * Settings → Billing. Shows the same live subscription state and actions as
 * the /billing page; starting a new subscription hands off to /billing so the
 * operator sees the plan and price before checkout.
 */
export function BillingSettingsTab() {
  const { data } = useBillingStatus();
  const href = data ? `/billing?billing_account_id=${encodeURIComponent(data.billing_account.id)}` : "/billing";
  return (
    <Card>
      <CardHeader>
        <CardTitle>Subscription</CardTitle>
        <CardDescription>
          Your current plan and status, straight from Stripe.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <SubscriptionSummary subscribeMode="billing-page" />
      </CardContent>
      <CardFooter>
        <Button asChild variant="link" className="h-auto px-0">
          <Link href={href}>Open billing page</Link>
        </Button>
      </CardFooter>
    </Card>
  );
}
