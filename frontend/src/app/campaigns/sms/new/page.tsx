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
import { useAuth } from "@/providers/auth-provider";
import type { Contact, Agent, Offer, SMSCampaign } from "@/types";

// Default workspace ID - matches backend seed
const DEFAULT_WORKSPACE_ID = "ba0e0e99-c7c9-45ec-9625-567d54d6e9c2";

// Mock data for development - will be replaced with API calls
const mockContacts: Contact[] = [
  {
    id: 1,
    user_id: 1,
    workspace_id: DEFAULT_WORKSPACE_ID,
    first_name: "John",
    last_name: "Smith",
    email: "john.smith@example.com",
    phone_number: "+15551234567",
    company_name: "Acme Corp",
    status: "new",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: 2,
    user_id: 1,
    workspace_id: DEFAULT_WORKSPACE_ID,
    first_name: "Sarah",
    last_name: "Johnson",
    email: "sarah.j@example.com",
    phone_number: "+15559876543",
    company_name: "Tech Solutions",
    status: "contacted",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: 3,
    user_id: 1,
    workspace_id: DEFAULT_WORKSPACE_ID,
    first_name: "Mike",
    last_name: "Williams",
    email: "mike.w@example.com",
    phone_number: "+15555550123",
    status: "qualified",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: 4,
    user_id: 1,
    workspace_id: DEFAULT_WORKSPACE_ID,
    first_name: "Emily",
    last_name: "Brown",
    email: "emily.b@example.com",
    phone_number: "+15555551234",
    company_name: "Brown & Associates",
    status: "new",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: 5,
    user_id: 1,
    workspace_id: DEFAULT_WORKSPACE_ID,
    first_name: "David",
    last_name: "Lee",
    email: "david.l@example.com",
    phone_number: "+15555552345",
    status: "converted",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

const mockAgents: Agent[] = [
  {
    id: "agent-1",
    user_id: 1,
    name: "Sales Assistant",
    description: "Friendly sales agent that qualifies leads and books appointments",
    channel_mode: "text",
    pricing_tier: "balanced",
    system_prompt: "You are a helpful sales assistant. Be friendly and professional. Focus on understanding customer needs and qualifying leads.",
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "agent-2",
    user_id: 1,
    name: "Support Bot",
    description: "Customer support agent for answering common questions",
    channel_mode: "both",
    pricing_tier: "budget",
    system_prompt: "You are a customer support agent. Answer questions helpfully and concisely.",
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    id: "agent-3",
    user_id: 1,
    name: "Premium Concierge",
    description: "High-touch concierge service for VIP customers",
    channel_mode: "text",
    pricing_tier: "premium",
    system_prompt: "You are a premium concierge providing white-glove service. Be extremely polite and accommodating.",
    is_active: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

export default function NewSMSCampaignPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { workspaceId, isLoading: authLoading } = useAuth();
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

  const isLoading = authLoading || offersLoading || phoneNumbersLoading;

  // Use mock data for contacts and agents (replace with API calls later)
  const contacts = mockContacts;
  const agents = mockAgents;
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
