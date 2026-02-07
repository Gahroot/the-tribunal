"use client";

import type { UseFormReturn } from "react-hook-form";
import type { AgentFormValues } from "./create-agent-form";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { PRICING_TIERS } from "@/lib/pricing-tiers";
import { getTierIcon } from "./agent-form-utils";

interface PricingTierStepProps {
  form: UseFormReturn<AgentFormValues>;
  pricingTier: string;
}

export function PricingTierStep({ form, pricingTier }: PricingTierStepProps) {
  return (
    <Card>
      <CardContent className="p-6">
        <div className="mb-4">
          <h2 className="text-lg font-medium">Choose Your Pricing Tier</h2>
          <p className="text-sm text-muted-foreground">
            Select the right balance of cost and quality for your use case
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {PRICING_TIERS.map((tier) => {
            const TierIcon = getTierIcon(tier.id);
            const isSelected = pricingTier === tier.id;

            return (
              <button
                key={tier.id}
                type="button"
                disabled={tier.underConstruction}
                onClick={() =>
                  !tier.underConstruction &&
                  form.setValue("pricingTier", tier.id as AgentFormValues["pricingTier"])
                }
                className={cn(
                  "relative flex flex-col rounded-lg border p-4 text-left transition-all",
                  tier.underConstruction
                    ? "cursor-not-allowed opacity-60"
                    : "hover:border-primary/50",
                  isSelected &&
                    !tier.underConstruction &&
                    "border-primary bg-primary/5 ring-2 ring-primary"
                )}
              >
                {tier.recommended && (
                  <Badge className="absolute -top-2 right-3 text-[10px]">Popular</Badge>
                )}
                <div className="mb-3 flex items-center gap-2">
                  <div
                    className={cn(
                      "flex h-8 w-8 items-center justify-center rounded-md",
                      isSelected ? "bg-primary text-primary-foreground" : "bg-muted"
                    )}
                  >
                    <TierIcon className="h-4 w-4" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{tier.name}</span>
                      {tier.underConstruction && (
                        <Badge variant="secondary" className="px-1.5 py-0 text-[9px]">
                          Coming Soon
                        </Badge>
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      ${tier.costPerHour.toFixed(2)}/hr
                    </div>
                  </div>
                </div>
                <p className="mb-3 text-xs text-muted-foreground">{tier.description}</p>
                <div className="space-y-1 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Speed</span>
                    <span className="font-medium">{tier.performance.speed}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Quality</span>
                    <span className="font-medium">{tier.performance.quality}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Model</span>
                    <span className="font-mono text-[10px]">{tier.config.llmModel}</span>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
