"use client";

import { motion } from "framer-motion";
import {
  CheckCircle,
  Gift,
  Shield,
  Clock,
  AlertTriangle,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { LeadMagnet, ValueStackItem, GuaranteeType, UrgencyType, DiscountType } from "@/types";

// More flexible type to support wizard form data with empty string defaults
interface OfferPreviewData {
  name?: string;
  headline?: string;
  subheadline?: string;
  description?: string;
  regular_price?: number;
  offer_price?: number;
  savings_amount?: number;
  discount_type?: DiscountType | "";
  discount_value?: number;
  guarantee_type?: GuaranteeType | "";
  guarantee_days?: number;
  guarantee_text?: string;
  urgency_type?: UrgencyType | "";
  urgency_text?: string;
  scarcity_count?: number;
  value_stack_items?: ValueStackItem[];
  cta_text?: string;
  cta_subtext?: string;
  terms?: string;
}

interface OfferPreviewProps {
  offer: OfferPreviewData;
  leadMagnets?: LeadMagnet[];
}

const guaranteeLabels: Record<string, string> = {
  money_back: "Money-Back Guarantee",
  satisfaction: "Satisfaction Guarantee",
  results: "Results Guarantee",
};

const urgencyLabels: Record<string, string> = {
  limited_time: "Limited Time Offer",
  limited_quantity: "Limited Availability",
  expiring: "Offer Expiring Soon",
};

export function OfferPreview({ offer, leadMagnets = [] }: OfferPreviewProps) {
  // Calculate total value
  const valueStackTotal = (offer.value_stack_items || [])
    .filter((item) => item.included)
    .reduce((sum, item) => sum + (item.value || 0), 0);

  const leadMagnetTotal = leadMagnets.reduce(
    (sum, lm) => sum + (lm.estimated_value || 0),
    0
  );

  const totalValue = valueStackTotal + leadMagnetTotal;
  const savings = offer.savings_amount || (offer.regular_price && offer.offer_price
    ? offer.regular_price - offer.offer_price
    : 0);

  const formatDiscount = () => {
    switch (offer.discount_type) {
      case "percentage":
        return `${offer.discount_value}% OFF`;
      case "fixed":
        return `$${offer.discount_value} OFF`;
      case "free_service":
        return "FREE";
      default:
        return "";
    }
  };

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        {/* Header with headline */}
        <div className="bg-gradient-to-r from-primary/10 to-primary/5 p-6 text-center">
          {offer.headline ? (
            <h2 className="text-2xl font-bold">{offer.headline}</h2>
          ) : (
            <h2 className="text-2xl font-bold">{offer.name || "Your Offer"}</h2>
          )}
          {offer.subheadline && (
            <p className="text-muted-foreground mt-2">{offer.subheadline}</p>
          )}
        </div>

        <div className="p-6 space-y-6">
          {/* Value Stack */}
          {((offer.value_stack_items && offer.value_stack_items.length > 0) ||
            leadMagnets.length > 0) && (
            <div className="space-y-3">
              <h3 className="font-semibold flex items-center gap-2">
                <Sparkles className="size-4 text-yellow-500" />
                Here&apos;s Everything You Get:
              </h3>

              <div className="space-y-2">
                {/* Value stack items */}
                {(offer.value_stack_items || [])
                  .filter((item) => item.included)
                  .map((item, index) => (
                    <motion.div
                      key={index}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: index * 0.1 }}
                      className="flex items-center justify-between p-3 bg-muted/50 rounded-lg"
                    >
                      <div className="flex items-center gap-2">
                        <CheckCircle className="size-5 text-green-500" />
                        <div>
                          <p className="font-medium">{item.name}</p>
                          {item.description && (
                            <p className="text-sm text-muted-foreground">
                              {item.description}
                            </p>
                          )}
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="text-muted-foreground line-through text-sm">
                          ${item.value?.toLocaleString()}
                        </p>
                      </div>
                    </motion.div>
                  ))}

                {/* Lead magnets as bonuses */}
                {leadMagnets.map((magnet, index) => (
                  <motion.div
                    key={magnet.id}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{
                      delay: (offer.value_stack_items?.length || 0) * 0.1 + index * 0.1,
                    }}
                    className="flex items-center justify-between p-3 bg-blue-500/5 rounded-lg border border-blue-500/20"
                  >
                    <div className="flex items-center gap-2">
                      <Gift className="size-5 text-blue-500" />
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="font-medium">{magnet.name}</p>
                          <Badge
                            variant="secondary"
                            className="bg-blue-500/10 text-blue-600"
                          >
                            BONUS
                          </Badge>
                        </div>
                        {magnet.description && (
                          <p className="text-sm text-muted-foreground">
                            {magnet.description}
                          </p>
                        )}
                      </div>
                    </div>
                    {magnet.estimated_value && magnet.estimated_value > 0 && (
                      <div className="text-right">
                        <p className="text-muted-foreground line-through text-sm">
                          ${magnet.estimated_value.toLocaleString()}
                        </p>
                      </div>
                    )}
                  </motion.div>
                ))}
              </div>
            </div>
          )}

          <Separator />

          {/* Pricing */}
          <div className="text-center space-y-2">
            {totalValue > 0 && (
              <div>
                <p className="text-sm text-muted-foreground">Total Value</p>
                <p className="text-2xl font-bold text-muted-foreground line-through">
                  ${totalValue.toLocaleString()}
                </p>
              </div>
            )}

            {offer.regular_price && offer.regular_price > 0 && (
              <div>
                <p className="text-sm text-muted-foreground">Regular Price</p>
                <p className="text-xl text-muted-foreground line-through">
                  ${offer.regular_price.toLocaleString()}
                </p>
              </div>
            )}

            <div className="py-2">
              <p className="text-sm text-muted-foreground">Your Price Today</p>
              <div className="flex items-center justify-center gap-3">
                <p className="text-4xl font-bold text-green-600">
                  {offer.offer_price !== undefined && offer.offer_price !== null
                    ? `$${offer.offer_price.toLocaleString()}`
                    : offer.discount_type === "free_service"
                    ? "FREE"
                    : formatDiscount() || "Contact Us"}
                </p>
                {savings > 0 && (
                  <Badge className="bg-red-500 text-white">
                    Save ${savings.toLocaleString()}
                  </Badge>
                )}
              </div>
            </div>
          </div>

          {/* Guarantee */}
          {offer.guarantee_type && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-start gap-3 p-4 bg-green-500/5 rounded-lg border border-green-500/20"
            >
              <Shield className="size-6 text-green-600 mt-0.5" />
              <div>
                <p className="font-semibold text-green-700 dark:text-green-400">
                  {guaranteeLabels[offer.guarantee_type] || offer.guarantee_type}
                  {offer.guarantee_days && ` - ${offer.guarantee_days} Days`}
                </p>
                {offer.guarantee_text && (
                  <p className="text-sm text-muted-foreground mt-1">
                    {offer.guarantee_text}
                  </p>
                )}
              </div>
            </motion.div>
          )}

          {/* Urgency/Scarcity */}
          {(offer.urgency_type || offer.scarcity_count) && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-start gap-3 p-4 bg-amber-500/5 rounded-lg border border-amber-500/20"
            >
              {offer.urgency_type === "limited_quantity" ? (
                <AlertTriangle className="size-6 text-amber-600 mt-0.5" />
              ) : (
                <Clock className="size-6 text-amber-600 mt-0.5" />
              )}
              <div>
                <p className="font-semibold text-amber-700 dark:text-amber-400">
                  {offer.urgency_type
                    ? urgencyLabels[offer.urgency_type]
                    : "Limited Availability"}
                </p>
                {offer.urgency_text && (
                  <p className="text-sm text-muted-foreground mt-1">
                    {offer.urgency_text}
                  </p>
                )}
                {offer.scarcity_count && offer.scarcity_count > 0 && (
                  <p className="text-sm font-medium text-amber-600 mt-1">
                    Only {offer.scarcity_count} spots remaining!
                  </p>
                )}
              </div>
            </motion.div>
          )}

          {/* CTA */}
          <Button className="w-full h-14 text-lg font-semibold">
            {offer.cta_text || "Get Started Now"}
          </Button>

          {offer.cta_subtext && (
            <p className="text-center text-sm text-muted-foreground">
              {offer.cta_subtext}
            </p>
          )}

          {/* Terms */}
          {offer.terms && (
            <p className="text-xs text-center text-muted-foreground italic">
              {offer.terms}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
