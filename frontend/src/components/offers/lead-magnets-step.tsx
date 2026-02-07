"use client";

import { LeadMagnetSelector } from "./lead-magnet-selector";
import type { LeadMagnet } from "@/types";

interface LeadMagnetsStepProps {
  leadMagnets: LeadMagnet[];
  selectedIds: string[];
  onSelect: (ids: string[]) => void;
  onCreateLeadMagnet: (lm: Partial<LeadMagnet>) => Promise<void>;
}

export function LeadMagnetsStep({
  leadMagnets,
  selectedIds,
  onSelect,
  onCreateLeadMagnet,
}: LeadMagnetsStepProps) {
  return (
    <LeadMagnetSelector
      leadMagnets={leadMagnets}
      selectedIds={selectedIds}
      onSelect={onSelect}
      onCreateLeadMagnet={onCreateLeadMagnet}
      multiSelect
    />
  );
}
