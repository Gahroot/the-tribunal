"use client";

import { Megaphone } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/ui/status-badge";

/**
 * Status pill for enrichment workflow progress (used on contact cards).
 */
export function EnrichmentStatusBadge({ status }: { status: string | null | undefined }) {
  if (!status) return null;

  const statusConfig: Record<string, { label: string; dotClass: string }> = {
    pending: { label: "Enriching...", dotClass: "bg-warning" },
    enriched: { label: "Enriched", dotClass: "bg-success" },
    failed: { label: "Failed", dotClass: "bg-destructive" },
    skipped: { label: "No website", dotClass: "bg-muted-foreground" },
  };

  const config = statusConfig[status];
  if (!config) return null;

  return (
    <StatusBadge dotClass={config.dotClass} className="text-xs">
      {config.label}
    </StatusBadge>
  );
}

/**
 * Color-coded numeric lead-score badge.
 */
export function LeadScoreBadge({ score }: { score: number | null | undefined }) {
  if (score == null) return null;

  const dotClass =
    score >= 100 ? "bg-success" : score >= 80 ? "bg-info" : "bg-warning";

  return (
    <StatusBadge dotClass={dotClass} className="text-xs font-semibold">
      {score}
    </StatusBadge>
  );
}

/**
 * Renders one badge per active ad pixel (Meta, Google).
 */
export function AdPixelBadges({
  adPixels,
}: {
  adPixels?: { meta_pixel?: boolean; google_ads?: boolean };
}) {
  if (!adPixels) return null;
  const badges: { label: string; active: boolean }[] = [
    { label: "Meta Ads", active: !!adPixels.meta_pixel },
    { label: "Google Ads", active: !!adPixels.google_ads },
  ];
  const activeBadges = badges.filter((b) => b.active);
  if (activeBadges.length === 0) return null;

  return (
    <>
      {activeBadges.map((badge) => (
        <Badge
          key={badge.label}
          variant="outline"
          className="text-xs gap-1"
        >
          <Megaphone className="h-3 w-3" />
          {badge.label}
        </Badge>
      ))}
    </>
  );
}
