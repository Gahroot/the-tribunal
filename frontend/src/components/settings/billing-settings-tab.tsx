import Link from "next/link";

import { SubscriptionSummary } from "@/components/shared/billing/subscription-summary";
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
          <Link href="/billing">Open billing page</Link>
        </Button>
      </CardFooter>
    </Card>
  );
}
