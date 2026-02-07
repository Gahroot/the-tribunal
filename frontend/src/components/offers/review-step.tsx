"use client";

import { OfferPreview } from "./offer-preview";
import type { OfferFormData } from "./offer-builder-wizard";
import type { LeadMagnet } from "@/types";

interface ReviewStepProps {
  formData: OfferFormData;
  selectedLeadMagnets: LeadMagnet[];
}

export function ReviewStep({ formData, selectedLeadMagnets }: ReviewStepProps) {
  return (
    <div className="space-y-6">
      <div className="text-center mb-6">
        <h3 className="text-lg font-semibold">Review Your Offer</h3>
        <p className="text-muted-foreground">
          Here&apos;s how your offer will appear
        </p>
      </div>
      <OfferPreview offer={formData} leadMagnets={selectedLeadMagnets} />
    </div>
  );
}
