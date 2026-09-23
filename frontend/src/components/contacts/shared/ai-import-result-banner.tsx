"use client";

import { AlertCircle, CheckCircle2, XCircle } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import type { AIImportLeadsResponse } from "@/lib/api/find-leads-ai";
import { cn } from "@/lib/utils";

interface AIImportResultBannerProps {
  result: AIImportLeadsResponse;
  showDetails: boolean;
  onToggleDetails: () => void;
}

export function AIImportResultBanner({
  result,
  showDetails,
  onToggleDetails,
}: AIImportResultBannerProps) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-4">
          {result.imported > 0 ? (
            <CheckCircle2 className="h-8 w-8 text-success" />
          ) : (
            <AlertCircle className="h-8 w-8 text-warning" />
          )}
          <div className="flex-1">
            <p className="font-medium">
              {result.imported > 0
                ? `Successfully imported ${result.imported} leads`
                : "No leads imported"}
            </p>
            <div className="flex gap-4 text-sm text-muted-foreground flex-wrap">
              {result.rejected_low_score > 0 && (
                <span className="flex items-center gap-1">
                  <XCircle className="h-3 w-3" />
                  {result.rejected_low_score} rejected below quality threshold
                </span>
              )}
              {result.enrichment_failed > 0 && (
                <span>{result.enrichment_failed} enrichment failed</span>
              )}
              {result.skipped_duplicates > 0 && (
                <span>{result.skipped_duplicates} duplicates skipped</span>
              )}
              {result.skipped_no_phone > 0 && (
                <span>{result.skipped_no_phone} skipped (no phone)</span>
              )}
            </div>
          </div>
          {result.imported > 0 && (
            <Button variant="outline" size="sm" asChild>
              <Link href="/contacts">View Contacts</Link>
            </Button>
          )}
        </div>
      </CardContent>
      {result.lead_details && result.lead_details.length > 0 && (
        <div className="border-t px-4 pb-4">
          <Button
            variant="ghost"
            size="sm"
            className="w-full mt-2 text-xs"
            onClick={onToggleDetails}
          >
            {showDetails ? "Hide" : "Show"} details ({result.lead_details.length} leads)
          </Button>
          {showDetails && (
            <div className="mt-2 max-h-64 overflow-y-auto space-y-1">
              {result.lead_details.map((detail, i) => (
                <div
                  key={i}
                  className={cn(
                    "flex items-center justify-between text-xs px-2 py-1.5 rounded",
                    detail.status === "skipped_duplicate" && "bg-muted text-muted-foreground",
                    detail.status === "skipped_no_phone" && "bg-muted text-muted-foreground",
                  )}
                >
                  <div className="flex items-center gap-2 min-w-0">
                    {detail.status === "imported" && (
                      <CheckCircle2 className="h-3 w-3 shrink-0 text-success" />
                    )}
                    {detail.status === "rejected_low_score" && (
                      <XCircle className="h-3 w-3 shrink-0 text-warning" />
                    )}
                    {detail.status === "enrichment_failed" && (
                      <AlertCircle className="h-3 w-3 shrink-0 text-destructive" />
                    )}
                    <span className="truncate font-medium">{detail.name}</span>
                    {detail.decision_maker_name && (
                      <span className="text-muted-foreground truncate">
                        ({detail.decision_maker_title || "Owner"}: {detail.decision_maker_name})
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {detail.revenue_tier && (
                      <Badge variant="outline" className="text-[10px] px-1 py-0">
                        {detail.revenue_tier}
                      </Badge>
                    )}
                    {detail.lead_score != null && (
                      <StatusBadge
                        dotClass={
                          detail.lead_score >= 100
                            ? "bg-success"
                            : detail.lead_score >= 80
                              ? "bg-info"
                              : "bg-warning"
                        }
                        className="text-[10px] px-1 py-0 font-semibold"
                      >
                        Score: {detail.lead_score}
                      </StatusBadge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
