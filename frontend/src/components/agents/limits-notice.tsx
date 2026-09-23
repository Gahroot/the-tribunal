"use client";

import { X } from "lucide-react";
import Link from "next/link";
import { createElement } from "react";

import { Button } from "@/components/ui/button";
import type { PricingTier } from "@/lib/pricing-tiers";

import { getTierIcon } from "./agent-form-utils";

interface LimitsNoticeProps {
  tier: PricingTier;
  onDismiss: () => void;
}

/**
 * Dismissible plan/limits banner shown above the create wizard. Pricing and
 * upgrades live here (and on the billing page) instead of as a wizard step,
 * so the wizard leads with the agent's job.
 */
export function LimitsNotice({ tier, onDismiss }: LimitsNoticeProps) {
  return (
    <div className="mb-6 flex items-start gap-3 rounded-lg border bg-background p-4 text-foreground">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md">
        {createElement(getTierIcon(tier.id), { className: "h-4 w-4 text-primary" })}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">
          Voice tier: {tier.name} (${tier.costPerHour.toFixed(2)}/hr while on a call)
        </p>
        <p className="mt-0.5 text-sm text-muted-foreground">
          This agent will be created on the {tier.name} tier. Voices, languages, and model
          quality follow the tier, and you can change them later in agent settings.
        </p>
        <Button asChild variant="link" size="sm" className="mt-1 h-auto px-0">
          <Link href="/billing">View plans and billing</Link>
        </Button>
      </div>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label="Dismiss limits notice"
        onClick={onDismiss}
      >
        <X className="h-4 w-4" />
      </Button>
    </div>
  );
}
