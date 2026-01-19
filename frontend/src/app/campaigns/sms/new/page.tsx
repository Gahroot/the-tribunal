"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ArrowLeft, Loader2 } from "lucide-react";
import Link from "next/link";

import { AppSidebar } from "@/components/layout/app-sidebar";
import { Button } from "@/components/ui/button";
import { SMSCampaignWizard } from "@/components/campaigns/sms-campaign-wizard";
import { smsCampaignsApi, type CreateSMSCampaignRequest } from "@/lib/api/sms-campaigns";
import { offersApi } from "@/lib/api/offers";
import { phoneNumbersApi } from "@/lib/api/phone-numbers";
import { contactsApi } from "@/lib/api/contacts";
import { agentsApi } from "@/lib/api/agents";
import { useWorkspaceId } from "@/hooks/use-workspace-id";
import type { Offer, SMSCampaign } from "@/types";

export default function NewSMSCampaignPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Fetch offers from API (with fallback to empty array)
  const { data: offersData, isLoading: offersLoading } = useQuery({
    queryKey: ["offers", workspaceId],
    queryFn: async () => {
      if (!workspaceId) return [];
      try {
        const response = await offersApi.list(workspaceId);
        return response.items;
      } catch {
        // Return empty array if API not available yet
        return [];
      }
    },
    enabled: !!workspaceId,
  });

  // Fetch phone numbers from API - filter to SMS-enabled only
  const { data: phoneNumbersData, isLoading: phoneNumbersLoading } = useQuery({
    queryKey: ["phone-numbers", workspaceId, { sms_enabled: true }],
    queryFn: async () => {
      if (!workspaceId) return [];
      const response = await phoneNumbersApi.list(workspaceId, { sms_enabled: true });
      return response.items;
    },
    enabled: !!workspaceId,
  });

  // Fetch contacts from API (page_size max is 100 per backend limit)
  const { data: contactsData, isLoading: contactsLoading } = useQuery({
    queryKey: ["contacts", workspaceId],
    queryFn: async () => {
      if (!workspaceId) return [];
      const response = await contactsApi.list(workspaceId, { page_size: 100 });
      return response.items;
    },
    enabled: !!workspaceId,
  });

  // Fetch agents from API - filter to active agents only
  const { data: agentsData, isLoading: agentsLoading } = useQuery({
    queryKey: ["agents", workspaceId, { active_only: true }],
    queryFn: async () => {
      if (!workspaceId) return [];
      const response = await agentsApi.list(workspaceId, { active_only: true });
      return response.items;
    },
    enabled: !!workspaceId,
  });

  // Create offer mutation
  const createOfferMutation = useMutation({
    mutationFn: async (offer: Partial<Offer>) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      await offersApi.create(workspaceId, {
        name: offer.name!,
        description: offer.description,
        discount_type: offer.discount_type!,
        discount_value: offer.discount_value!,
        terms: offer.terms,
        is_active: offer.is_active ?? true,
      });
    },
    onSuccess: () => {
      if (workspaceId) {
        queryClient.invalidateQueries({ queryKey: ["offers", workspaceId] });
      }
      toast.success("Offer created successfully");
    },
    onError: (error) => {
      toast.error("Failed to create offer");
      console.error("Create offer error:", error);
    },
  });

  // Create campaign mutation
  const createCampaignMutation = useMutation({
    mutationFn: async ({
      data,
      contactIds,
    }: {
      data: CreateSMSCampaignRequest;
      contactIds: number[];
    }) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      // Create the campaign
      const campaign = await smsCampaignsApi.create(workspaceId, data);

      // Add contacts to the campaign
      if (contactIds.length > 0) {
        await smsCampaignsApi.addContacts(workspaceId, campaign.id, contactIds);
      }

      return campaign;
    },
    onSuccess: (campaign) => {
      toast.success("Campaign created successfully!");
      if (workspaceId) {
        queryClient.invalidateQueries({ queryKey: ["campaigns", workspaceId] });
      }
      router.push(`/campaigns/${campaign.id}`);
    },
    onError: (error) => {
      toast.error("Failed to create campaign");
      console.error("Create campaign error:", error);
    },
  });

  const handleSubmit = async (
    data: CreateSMSCampaignRequest,
    contactIds: number[]
  ): Promise<SMSCampaign> => {
    setIsSubmitting(true);
    try {
      const campaign = await createCampaignMutation.mutateAsync({ data, contactIds });
      return campaign as SMSCampaign;
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCreateOffer = async (offer: Partial<Offer>) => {
    await createOfferMutation.mutateAsync(offer);
  };

  const isLoading = !workspaceId || offersLoading || phoneNumbersLoading || contactsLoading || agentsLoading;

  const contacts = Array.isArray(contactsData) ? contactsData : [];
  const agents = Array.isArray(agentsData) ? agentsData : [];
  const offers = Array.isArray(offersData) ? offersData : [];
  const phoneNumbers = Array.isArray(phoneNumbersData) ? phoneNumbersData : [];

  return (
    <AppSidebar>
      <div className="flex flex-col h-[calc(100vh-4rem)]">
        {/* Header */}
        <div className="flex items-center gap-4 px-6 py-4 border-b bg-background">
          <Button variant="ghost" size="icon" asChild>
            <Link href="/campaigns">
              <ArrowLeft className="size-5" />
            </Link>
          </Button>
          <div>
            <h1 className="text-xl font-semibold">Create SMS Campaign</h1>
            <p className="text-sm text-muted-foreground">
              Set up a new SMS campaign to reach your contacts
            </p>
          </div>
        </div>

        {/* Wizard content */}
        {isLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="flex flex-col items-center gap-4">
              <Loader2 className="size-8 animate-spin text-muted-foreground" />
              <p className="text-muted-foreground">Loading campaign data...</p>
            </div>
          </div>
        ) : (
          <SMSCampaignWizard
            contacts={contacts}
            agents={agents}
            offers={offers}
            phoneNumbers={phoneNumbers}
            onSubmit={handleSubmit}
            onCreateOffer={handleCreateOffer}
            onCancel={() => router.push("/campaigns")}
            isSubmitting={isSubmitting}
          />
        )}
      </div>
    </AppSidebar>
  );
}
