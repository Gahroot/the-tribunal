"use client";

import { useState } from "react";
import { formatDistanceToNow } from "date-fns";
import {
  ChevronDown,
  ChevronUp,
  BarChart3,
  Phone,
  MessageSquare,
  ThumbsUp,
  ThumbsDown,
  Clock,
  AlertTriangle,
  Loader2,
  ArrowRight,
} from "lucide-react";

import type {
  CampaignReportResponse,
  CampaignReportFinding,
  CampaignReportEvidence,
  CampaignReportRecommendation,
} from "@/lib/api/campaign-reports";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

interface CampaignReportCardProps {
  report: CampaignReportResponse;
}

export function CampaignReportCard({ report }: CampaignReportCardProps) {
  const [expandedSection, setExpandedSection] = useState<string | null>(null);

  const toggleSection = (section: string) => {
    setExpandedSection((prev) => (prev === section ? null : section));
  };

  const campaignTypeBadge = report.campaign_type === "voice_sms_fallback" ? (
    <Badge variant="outline" className="gap-1">
      <Phone className="h-3 w-3" />
      Voice
    </Badge>
  ) : (
    <Badge variant="outline" className="gap-1">
      <MessageSquare className="h-3 w-3" />
      SMS
    </Badge>
  );

  const statusBadge = (() => {
    switch (report.status) {
      case "completed":
        return <Badge className="bg-green-600">Completed</Badge>;
      case "generating":
        return (
          <Badge variant="secondary" className="gap-1">
            <Loader2 className="h-3 w-3 animate-spin" />
            Generating
          </Badge>
        );
      case "failed":
        return <Badge variant="destructive">Failed</Badge>;
      default:
        return <Badge variant="secondary">{report.status}</Badge>;
    }
  })();

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-muted-foreground" />
              <CardTitle className="text-base">
                {report.campaign_name ?? "Campaign Report"}
              </CardTitle>
              {campaignTypeBadge}
              {statusBadge}
            </div>
            <CardDescription>
              {report.generated_at
                ? `Generated ${formatDistanceToNow(new Date(report.generated_at), { addSuffix: true })}`
                : `Created ${formatDistanceToNow(new Date(report.created_at), { addSuffix: true })}`}
            </CardDescription>
          </div>
        </div>
      </CardHeader>

      {report.status === "completed" && (
        <CardContent className="space-y-4">
          {/* Executive Summary - always visible */}
          {report.executive_summary && (
            <div className="rounded-md border bg-muted/30 p-4">
              <p className="whitespace-pre-line text-sm leading-relaxed">
                {report.executive_summary}
              </p>
            </div>
          )}

          {/* Key Findings */}
          {report.key_findings && report.key_findings.length > 0 && (
            <ReportSection
              title="Key Findings"
              count={report.key_findings.length}
              isOpen={expandedSection === "findings"}
              onToggle={() => toggleSection("findings")}
            >
              <div className="space-y-3">
                {report.key_findings.map((finding, i) => (
                  <FindingItem key={i} finding={finding} />
                ))}
              </div>
            </ReportSection>
          )}

          {/* What Worked */}
          {report.what_worked && report.what_worked.length > 0 && (
            <ReportSection
              title="What Worked"
              count={report.what_worked.length}
              isOpen={expandedSection === "worked"}
              onToggle={() => toggleSection("worked")}
              icon={<ThumbsUp className="h-4 w-4 text-green-600" />}
            >
              <div className="space-y-3">
                {report.what_worked.map((item, i) => (
                  <EvidenceItem key={i} item={item} variant="positive" />
                ))}
              </div>
            </ReportSection>
          )}

          {/* What Didn't Work */}
          {report.what_didnt_work && report.what_didnt_work.length > 0 && (
            <ReportSection
              title="What Didn't Work"
              count={report.what_didnt_work.length}
              isOpen={expandedSection === "didnt_work"}
              onToggle={() => toggleSection("didnt_work")}
              icon={<ThumbsDown className="h-4 w-4 text-red-600" />}
            >
              <div className="space-y-3">
                {report.what_didnt_work.map((item, i) => (
                  <EvidenceItem key={i} item={item} variant="negative" />
                ))}
              </div>
            </ReportSection>
          )}

          {/* Recommendations */}
          {report.recommendations && report.recommendations.length > 0 && (
            <ReportSection
              title="Recommendations"
              count={report.recommendations.length}
              isOpen={expandedSection === "recommendations"}
              onToggle={() => toggleSection("recommendations")}
              icon={<ArrowRight className="h-4 w-4 text-blue-600" />}
            >
              <div className="space-y-3">
                {report.recommendations.map((rec, i) => (
                  <RecommendationItem key={i} rec={rec} />
                ))}
              </div>
            </ReportSection>
          )}

          {/* Timing Analysis */}
          {report.timing_analysis && report.timing_analysis.recommendation && (
            <ReportSection
              title="Timing Analysis"
              isOpen={expandedSection === "timing"}
              onToggle={() => toggleSection("timing")}
              icon={<Clock className="h-4 w-4 text-purple-600" />}
            >
              <div className="rounded-md border bg-muted/30 p-3">
                <p className="text-sm">{report.timing_analysis.recommendation}</p>
                {report.timing_analysis.best_hours && report.timing_analysis.best_hours.length > 0 && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    Best hours:{" "}
                    {report.timing_analysis.best_hours.map((h) => `${h}:00`).join(", ")}
                  </p>
                )}
              </div>
            </ReportSection>
          )}

          {/* Generated Suggestions Link */}
          {report.generated_suggestion_ids && report.generated_suggestion_ids.length > 0 && (
            <div className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 dark:border-amber-800 dark:bg-amber-950/30">
              <AlertTriangle className="h-4 w-4 text-amber-600" />
              <p className="text-sm">
                This report spawned{" "}
                <span className="font-medium">
                  {report.generated_suggestion_ids.length} prompt suggestion
                  {report.generated_suggestion_ids.length !== 1 && "s"}
                </span>{" "}
                - check the Prompt Suggestions tab.
              </p>
            </div>
          )}
        </CardContent>
      )}

      {report.status === "failed" && report.error_message && (
        <CardContent>
          <div className="rounded-md border border-red-200 bg-red-50 p-3 dark:border-red-800 dark:bg-red-950/30">
            <p className="text-sm text-red-700 dark:text-red-300">{report.error_message}</p>
          </div>
        </CardContent>
      )}

      {report.status === "generating" && (
        <CardContent>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Analyzing campaign data and generating intelligence report...
          </div>
        </CardContent>
      )}
    </Card>
  );
}

// Sub-components

interface ReportSectionProps {
  title: string;
  count?: number;
  isOpen: boolean;
  onToggle: () => void;
  icon?: React.ReactNode;
  children: React.ReactNode;
}

function ReportSection({ title, count, isOpen, onToggle, icon, children }: ReportSectionProps) {
  return (
    <Collapsible open={isOpen} onOpenChange={onToggle}>
      <CollapsibleTrigger asChild>
        <Button variant="ghost" size="sm" className="w-full justify-between">
          <span className="flex items-center gap-2 text-sm font-medium">
            {icon}
            {title}
            {count !== undefined && (
              <Badge variant="secondary" className="text-xs">
                {count}
              </Badge>
            )}
          </span>
          {isOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-2">{children}</CollapsibleContent>
    </Collapsible>
  );
}

function FindingItem({ finding }: { finding: CampaignReportFinding }) {
  const sentimentColor = {
    positive: "border-l-green-500",
    negative: "border-l-red-500",
    neutral: "border-l-gray-400",
  };

  return (
    <div
      className={cn(
        "rounded-md border border-l-4 bg-muted/30 p-3",
        sentimentColor[finding.sentiment ?? "neutral"]
      )}
    >
      <h4 className="text-sm font-medium">{finding.title}</h4>
      <p className="mt-1 text-sm text-muted-foreground">{finding.description}</p>
      {finding.metric && (
        <p className="mt-1 text-xs font-medium text-foreground">{finding.metric}</p>
      )}
    </div>
  );
}

function EvidenceItem({
  item,
  variant,
}: {
  item: CampaignReportEvidence;
  variant: "positive" | "negative";
}) {
  return (
    <div
      className={cn(
        "rounded-md border border-l-4 bg-muted/30 p-3",
        variant === "positive" ? "border-l-green-500" : "border-l-red-500"
      )}
    >
      <h4 className="text-sm font-medium">{item.title}</h4>
      <p className="mt-1 text-sm text-muted-foreground">{item.description}</p>
      {item.evidence && (
        <p className="mt-1 text-xs italic text-muted-foreground">{item.evidence}</p>
      )}
    </div>
  );
}

function RecommendationItem({ rec }: { rec: CampaignReportRecommendation }) {
  const priorityColor = {
    high: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
    medium: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
    low: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  };

  return (
    <div className="rounded-md border bg-muted/30 p-3">
      <div className="flex items-center gap-2">
        <h4 className="text-sm font-medium">{rec.title}</h4>
        <Badge className={cn("text-xs", priorityColor[rec.priority])}>
          {rec.priority}
        </Badge>
      </div>
      <p className="mt-1 text-sm text-muted-foreground">{rec.description}</p>
    </div>
  );
}
