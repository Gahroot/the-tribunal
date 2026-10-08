"use client";

import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Zap } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef } from "react";
import { toast } from "sonner";

import { AppSidebar } from "@/components/layout/app-sidebar";
import { SubscriptionSummary } from "@/components/shared/billing/subscription-summary";
import { useBillingStatus } from "@/components/shared/billing/use-billing";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageLoadingState } from "@/components/ui/page-state";
import { queryKeys } from "@/lib/query-keys";

// ─── Constants ────────────────────────────────────────────────────────────────

const PLAN_PRICE = process.env.NEXT_PUBLIC_PLAN_PRICE ?? "$297/month";

const PLAN_FEATURES = [
  "AI-powered SMS agent that texts your dead leads",
  "Automatic appointment booking directly on your Cal.com calendar",
  "Unlimited lead uploads via CSV",
  "Smart follow-up sequences (2-touch cadence, fully automated)",
  "Realtor-focused messaging templates designed to get replies",
];

// ─── Sub-components ───────────────────────────────────────────────────────────

function PlanFeature({ text }: { text: string }) {
  return (
    <li className="flex items-start gap-3">
      <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" />
      <span className="text-sm text-muted-foreground">{text}</span>
    </li>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

/**
 * Stripe Checkout returns here with `?checkout=success|canceled`. Confirm the
 * outcome once, refresh subscription state, and clear the query param.
 */
function useCheckoutReturnNotice() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const outcome = searchParams.get("checkout");
  const handled = useRef(false);

  useEffect(() => {
    if (handled.current || (outcome !== "success" && outcome !== "canceled")) return;
    handled.current = true;
    if (outcome === "success") {
      toast.success(
        "Thanks! Your subscription is being activated. It can take a few seconds to show here.",
      );
      void queryClient.invalidateQueries({ queryKey: queryKeys.billing.status() });
    } else {
      toast("Checkout canceled. You weren't charged.");
    }
    const accountId = searchParams.get("billing_account_id");
    router.replace(accountId ? `/billing?billing_account_id=${encodeURIComponent(accountId)}` : "/billing");
  }, [outcome, queryClient, router, searchParams]);
}

function BillingContent() {
  const router = useRouter();
  useCheckoutReturnNotice();
  const { data: billingStatus } = useBillingStatus();
  const subscribed = billingStatus?.subscribed ?? false;

  return (
    <div className="flex flex-col items-center gap-8 p-6 md:p-12 max-w-2xl mx-auto w-full">
      {/* Header */}
      <div className="text-center space-y-2">
        <div className="flex justify-center">
          <div className="rounded-full p-4">
            <Zap className="h-8 w-8 text-muted-foreground" />
          </div>
        </div>
        <h1 className="text-3xl font-bold tracking-tight">
          Realtor Lead Reactivation
        </h1>
        <p className="text-muted-foreground max-w-md mx-auto">
          Let AI text your cold leads, provide value, and book appointments on your
          calendar, automatically.
        </p>
      </div>

      {/* Pricing Card */}
      <Card className="w-full border-2 border-primary/20">
        <CardHeader className="pb-4">
          <CardTitle className="text-xl">Monthly Subscription</CardTitle>
          <div className="flex items-baseline gap-1 mt-1">
            <span className="text-4xl font-bold">{PLAN_PRICE.split("/")[0]}</span>
            {PLAN_PRICE.includes("/") && (
              <span className="text-muted-foreground text-sm">
                /{PLAN_PRICE.split("/")[1]}
              </span>
            )}
          </div>
        </CardHeader>

        <CardContent className="space-y-6">
          {/* Feature list */}
          <ul className="space-y-3">
            {PLAN_FEATURES.map((feature) => (
              <PlanFeature key={feature} text={feature} />
            ))}
          </ul>

          {/* Live subscription state + working actions (shared with Settings → Billing) */}
          <Suspense fallback={<p role="status">Loading billing account…</p>}>
            <SubscriptionSummary subscribeMode="checkout" />
          </Suspense>

          {subscribed && (
            <Button
              className="w-full"
              variant="secondary"
              onClick={() => router.push("/dashboard")}
            >
              Go to Dashboard
            </Button>
          )}

          {/* Fine print — only when checkout is actually offered */}
          {billingStatus && !billingStatus.subscribed && billingStatus.checkout_available && (
            <p className="text-xs text-center text-muted-foreground">
              Secure payment via Stripe. Cancel anytime.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function BillingPage() {
  return (
    <AppSidebar>
      {/* Suspense: BillingContent reads useSearchParams (?checkout=...). */}
      <Suspense fallback={<PageLoadingState message="Loading billing…" />}>
        <BillingContent />
      </Suspense>
    </AppSidebar>
  );
}
