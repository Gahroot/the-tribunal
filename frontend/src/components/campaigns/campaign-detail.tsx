"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  ArrowLeft,
  Loader2,
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

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { campaignStatusColors } from "@/lib/status-colors";
import { useWorkspaceId } from "@/hooks/use-workspace-id";
import { campaignsApi } from "@/lib/api/campaigns";

interface CampaignDetailProps {
  campaignId: string;
}

export function CampaignDetail({ campaignId }: CampaignDetailProps) {
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();

  // Load campaign data
  const { data: campaign, isLoading, error } = useQuery({
    queryKey: ["campaigns", workspaceId, campaignId],
    queryFn: async () => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return campaignsApi.get(workspaceId, campaignId);
    },
    enabled: !!workspaceId,
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
        queryKey: ["campaigns", workspaceId, campaignId],
      });
    },
    onError: () => {
      toast.error("Failed to start campaign");
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
        queryKey: ["campaigns", workspaceId, campaignId],
      });
    },
    onError: () => {
      toast.error("Failed to pause campaign");
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
        queryKey: ["campaigns", workspaceId, campaignId],
      });
    },
    onError: () => {
      toast.error("Failed to resume campaign");
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
        queryKey: ["campaigns", workspaceId, campaignId],
      });
    },
    onError: () => {
      toast.error("Failed to cancel campaign");
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="size-8 animate-spin text-muted-foreground" />
          <p className="text-muted-foreground">Loading campaign...</p>
        </div>
      </div>
    );
  }

  if (error || !campaign) {
    return (
      <div className="p-6 max-w-2xl mx-auto">
        <div className="flex items-center gap-4 mb-6">
          <Button variant="ghost" size="icon" asChild>
            <Link href="/campaigns">
              <ArrowLeft className="size-5" />
            </Link>
          </Button>
        </div>
        <div className="flex flex-col items-center gap-4 py-12">
          <AlertCircle className="size-12 text-red-500" />
          <h2 className="text-xl font-semibold">Campaign not found</h2>
          <p className="text-muted-foreground text-center">
            The campaign could not be loaded. It may have been deleted.
          </p>
          <Button asChild>
            <Link href="/campaigns">Back to campaigns</Link>
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-4 flex-1">
          <Button variant="ghost" size="icon" asChild>
            <Link href="/campaigns">
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
              Created {new Date(campaign.created_at).toLocaleDateString()}
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

        {/* Statistics */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Statistics</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-2xl font-bold">
                  {campaign.total_contacts}
                </p>
                <p className="text-xs text-muted-foreground">Total Contacts</p>
              </div>
              <div>
                <p className="text-2xl font-bold">{campaign.messages_sent}</p>
                <p className="text-xs text-muted-foreground">Sent</p>
              </div>
              <div>
                <p className="text-2xl font-bold">
                  {campaign.replies_received}
                </p>
                <p className="text-xs text-muted-foreground">Replies</p>
              </div>
              <div>
                <p className="text-2xl font-bold">
                  {campaign.contacts_qualified}
                </p>
                <p className="text-xs text-muted-foreground">Qualified</p>
              </div>
              {campaign.campaign_type === "voice_sms_fallback" && (
                <div>
                  <p className="text-2xl font-bold flex items-center gap-1.5">
                    <CalendarCheck className="size-5 text-green-600" />
                    {(campaign as unknown as { appointments_booked?: number }).appointments_booked ?? 0}
                  </p>
                  <p className="text-xs text-muted-foreground">Booked</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
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
                  {new Date(campaign.scheduled_start).toLocaleDateString()}
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
