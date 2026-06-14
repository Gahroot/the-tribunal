"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Play,
  Pause,
  RotateCcw,
  XCircle,
  AlertCircle,
  CalendarCheck,
  MessageSquare,
  Phone,
} from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { GuaranteeProgress } from "@/components/campaigns/guarantee-progress";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { PageEmptyState, PageLoadingState } from "@/components/ui/page-state";
import { useCampaignAnalytics } from "@/hooks/useCampaigns";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { campaignsApi, type CampaignAnalytics } from "@/lib/api/campaigns";
import { voiceCampaignsApi } from "@/lib/api/voice-campaigns";
import { queryKeys } from "@/lib/query-keys";
import { campaignStatusColors } from "@/lib/status-colors";
import { formatDate } from "@/lib/utils/date";
import { getApiErrorMessage } from "@/lib/utils/errors";
import type { Campaign, VoiceCampaignAnalytics } from "@/types";

interface CampaignDetailProps {
  campaignId: string;
}

export function CampaignDetail({ campaignId }: CampaignDetailProps) {
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();

  // Load campaign data
  const { data: campaign, isPending, error } = useQuery({
    queryKey: queryKeys.campaigns.detail(workspaceId ?? "", campaignId),
    queryFn: async () => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return campaignsApi.get(workspaceId, campaignId);
    },
    enabled: !!workspaceId,
  });

  const isVoiceCampaign = campaign?.campaign_type === "voice_sms_fallback";

  const { data: analytics } = useCampaignAnalytics(workspaceId ?? "", campaignId, {
    enabled: !!campaign && !isVoiceCampaign,
  });

  const { data: voiceAnalytics } = useQuery<VoiceCampaignAnalytics>({
    queryKey: queryKeys.voiceCampaigns.analytics(workspaceId ?? "", campaignId),
    queryFn: async () => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return voiceCampaignsApi.getAnalytics(workspaceId, campaignId);
    },
    enabled: !!workspaceId && !!campaign && isVoiceCampaign,
  });

  // Start campaign mutation
  const startMutation = useMutation({
    mutationFn: async () => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return campaignsApi.start(workspaceId, campaignId);
    },
    onSuccess: () => {
      toast.success("Campaign started!");
      queryClient.invalidateQueries({
        queryKey: queryKeys.campaigns.detail(workspaceId ?? "", campaignId),
      });
    },
    onError: (err: unknown) => {
      toast.error(getApiErrorMessage(err, "Failed to start campaign"));
    },
  });

  // Pause campaign mutation
  const pauseMutation = useMutation({
    mutationFn: async () => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return campaignsApi.pause(workspaceId, campaignId);
    },
    onSuccess: () => {
      toast.success("Campaign paused!");
      queryClient.invalidateQueries({
        queryKey: queryKeys.campaigns.detail(workspaceId ?? "", campaignId),
      });
    },
    onError: (err: unknown) => {
      toast.error(getApiErrorMessage(err, "Failed to pause campaign"));
    },
  });

  // Resume campaign mutation
  const resumeMutation = useMutation({
    mutationFn: async () => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return campaignsApi.resume(workspaceId, campaignId);
    },
    onSuccess: () => {
      toast.success("Campaign resumed!");
      queryClient.invalidateQueries({
        queryKey: queryKeys.campaigns.detail(workspaceId ?? "", campaignId),
      });
    },
    onError: (err: unknown) => {
      toast.error(getApiErrorMessage(err, "Failed to resume campaign"));
    },
  });

  // Cancel campaign mutation
  const cancelMutation = useMutation({
    mutationFn: async () => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return campaignsApi.cancel(workspaceId, campaignId);
    },
    onSuccess: () => {
      toast.success("Campaign cancelled!");
      queryClient.invalidateQueries({
        queryKey: queryKeys.campaigns.detail(workspaceId ?? "", campaignId),
      });
    },
    onError: (err: unknown) => {
      toast.error(getApiErrorMessage(err, "Failed to cancel campaign"));
    },
  });

  if (isPending) {
    return <PageLoadingState className="h-full" message="Loading campaign…" />;
  }

  if (error || !campaign) {
    return (
      <PageEmptyState
        className="p-6"
        icon={<AlertCircle className="size-8 text-destructive" />}
        title="Campaign not found"
        description="The campaign could not be loaded. It may have been deleted."
        action={
          <Button asChild>
            <Link href="/campaigns">
              <ArrowLeft className="size-4" />
              Back to campaigns
            </Link>
          </Button>
        }
      />
    );
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-4 flex-1">
          <Button variant="ghost" size="icon" asChild>
            <Link href="/campaigns" aria-label="Back to campaigns">
              <ArrowLeft className="size-5" />
            </Link>
          </Button>
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-2xl font-bold">{campaign.name}</h1>
              <Badge className={campaignStatusColors[campaign.status]}>
                {campaign.status}
              </Badge>
            </div>
            <p className="text-sm text-muted-foreground">
              Created {formatDate(campaign.created_at)}
            </p>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex gap-2">
          {campaign.status === "draft" && (
            <Button
              onClick={() => startMutation.mutate()}
              disabled={startMutation.isPending}
              size="sm"
            >
              <Play className="size-4 mr-2" />
              Start
            </Button>
          )}
          {campaign.status === "running" && (
            <Button
              variant="outline"
              onClick={() => pauseMutation.mutate()}
              disabled={pauseMutation.isPending}
              size="sm"
            >
              <Pause className="size-4 mr-2" />
              Pause
            </Button>
          )}
          {campaign.status === "paused" && (
            <Button
              onClick={() => resumeMutation.mutate()}
              disabled={resumeMutation.isPending}
              size="sm"
            >
              <RotateCcw className="size-4 mr-2" />
              Resume
            </Button>
          )}
          {(campaign.status === "paused" || campaign.status === "draft") && (
            <Button
              variant="destructive"
              onClick={() => cancelMutation.mutate()}
              disabled={cancelMutation.isPending}
              size="sm"
            >
              <XCircle className="size-4 mr-2" />
              Cancel
            </Button>
          )}
        </div>
      </div>

      {/* Campaign details */}
      <div className="grid gap-6 md:grid-cols-2">
        {/* Basic info */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Campaign Details</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="text-sm text-muted-foreground">Type</p>
              <div className="flex items-center gap-2 mt-1">
                {campaign.campaign_type === "sms" ? (
                  <MessageSquare className="size-4" />
                ) : (
                  <Phone className="size-4" />
                )}
                <p className="font-medium capitalize">
                  {campaign.campaign_type === "voice_sms_fallback"
                    ? "Voice with SMS Fallback"
                    : campaign.campaign_type}
                </p>
              </div>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Phone Number</p>
              <p className="font-medium mt-1">{campaign.from_phone_number}</p>
            </div>
            {campaign.initial_message && (
              <div>
                <p className="text-sm text-muted-foreground">Initial Message</p>
                <p className="text-sm mt-1 line-clamp-3">
                  {campaign.initial_message}
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {isVoiceCampaign ? (
          <VoiceCallStatistics analytics={voiceAnalytics} />
        ) : (
          <SmsStatistics campaign={campaign} analytics={analytics} />
        )}

        {campaign.guarantee_target && campaign.guarantee_target > 0 && (
          <GuaranteeProgress campaignId={campaignId} campaignType={campaign.campaign_type} />
        )}
      </div>

      {/* Scheduling info */}
      {(campaign.sending_hours_start ||
        campaign.sending_hours_end ||
        campaign.scheduled_start) && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Schedule</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {campaign.scheduled_start && (
              <div>
                <p className="text-sm text-muted-foreground">Start Date</p>
                <p className="font-medium mt-1">
                  {formatDate(campaign.scheduled_start)}
                </p>
              </div>
            )}
            {(campaign.sending_hours_start || campaign.sending_hours_end) && (
              <div>
                <p className="text-sm text-muted-foreground">Sending Hours</p>
                <p className="font-medium mt-1">
                  {campaign.sending_hours_start} - {campaign.sending_hours_end}
                </p>
              </div>
            )}
            {campaign.timezone && (
              <div>
                <p className="text-sm text-muted-foreground">Timezone</p>
                <p className="font-medium mt-1">{campaign.timezone}</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* AI Settings */}
      {campaign.ai_enabled && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">AI Settings</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <p className="text-sm text-muted-foreground">AI Enabled</p>
              <p className="font-medium mt-1">Yes</p>
            </div>
            {campaign.qualification_criteria && (
              <div>
                <p className="text-sm text-muted-foreground">
                  Qualification Criteria
                </p>
                <p className="text-sm mt-1 line-clamp-3">
                  {campaign.qualification_criteria}
                </p>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function SmsStatistics({
  campaign,
  analytics,
}: {
  campaign: Campaign;
  analytics: CampaignAnalytics | undefined;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Statistics</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <StatItem label="Total Contacts" value={campaign.total_contacts} />
          <StatItem label="Sent" value={campaign.messages_sent} />
          <StatItem label="Delivered" value={campaign.messages_delivered} />
          <StatItem label="Replies" value={campaign.replies_received} />
          <StatItem label="Qualified" value={campaign.contacts_qualified} />
          <StatItem label="Opted Out" value={campaign.contacts_opted_out} />
          {campaign.messages_failed > 0 && (
            <StatItem
              className="text-destructive"
              label="Failed"
              value={campaign.messages_failed}
            />
          )}
          {campaign.appointments_booked > 0 && (
            <StatItem
              icon={<CalendarCheck className="size-5 text-success" />}
              label="Booked"
              value={campaign.appointments_booked}
            />
          )}
          <StatItem label="Links Clicked" value={campaign.links_clicked ?? 0} />
          <RateStat label="Delivery Rate" rate={analytics?.delivery_rate} />
          <RateStat label="Reply Rate" rate={analytics?.reply_rate} />
          <RateStat label="Qualification Rate" rate={analytics?.qualification_rate} />
        </div>
      </CardContent>
    </Card>
  );
}

function VoiceCallStatistics({
  analytics,
}: {
  analytics: VoiceCampaignAnalytics | undefined;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Call Statistics</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <StatItem label="Total Contacts" value={analytics?.total_contacts} />
          <StatItem label="Dialed" value={analytics?.calls_attempted} />
          <StatItem label="Answered" value={analytics?.calls_answered} />
          <PercentageRateStat label="Answer Rate" rate={analytics?.answer_rate} />
          <StatItem label="No Answer" value={analytics?.calls_no_answer} />
          <StatItem label="Voicemail" value={analytics?.calls_voicemail} />
          <StatItem label="SMS Fallbacks" value={analytics?.sms_fallbacks_sent} />
          <StatItem
            icon={<CalendarCheck className="size-5 text-success" />}
            label="Booked"
            value={analytics?.appointments_booked}
          />
          <StatItem label="Qualified" value={analytics?.contacts_qualified} />
          <StatItem label="Opted Out" value={analytics?.contacts_opted_out} />
          <PercentageRateStat
            label="Qualification Rate"
            rate={analytics?.qualification_rate}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function StatItem({
  className = "",
  icon,
  label,
  value,
}: {
  className?: string;
  icon?: React.ReactNode;
  label: string;
  value: number | undefined;
}) {
  return (
    <div>
      <p className={`text-2xl font-bold ${className}`.trim()}>
        <span className="flex items-center gap-1.5">
          {icon}
          {value ?? "—"}
        </span>
      </p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

function RateStat({ label, rate }: { label: string; rate: number | undefined }) {
  const value = rate ?? 0;
  const colorClass = rateColorClass(value);
  return (
    <div>
      <p className={`text-2xl font-bold ${colorClass}`}>
        {(value * 100).toFixed(1)}%
      </p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

function PercentageRateStat({ label, rate }: { label: string; rate: number | undefined }) {
  const value = rate ?? 0;
  const colorClass = rateColorClass(value / 100);
  return (
    <div>
      <p className={`text-2xl font-bold ${colorClass}`}>{value.toFixed(1)}%</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

function rateColorClass(rate: number) {
  return rate >= 0.2
    ? "text-success"
    : rate >= 0.05
      ? "text-amber-500"
      : "text-muted-foreground";
}
