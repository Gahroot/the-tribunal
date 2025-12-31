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
import type { Contact, Agent, Offer, PhoneNumber, SMSCampaign } from "@/types";

// TODO: Replace with real workspace ID from auth context
const WORKSPACE_ID = "demo-workspace";

// Mock data for development - will be replaced with API calls
const mockContacts: Contact[] = [
  {
    id: 1,
    user_id: 1,
    workspace_id: WORKSPACE_ID,
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
    workspace_id: WORKSPACE_ID,
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
    workspace_id: WORKSPACE_ID,
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
    workspace_id: WORKSPACE_ID,
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
    workspace_id: WORKSPACE_ID,
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

const mockPhoneNumbers: PhoneNumber[] = [
  {
    id: "phone-1",
    workspace_id: WORKSPACE_ID,
    phone_number: "+15551112222",
    friendly_name: "Main Line",
    sms_enabled: true,
    voice_enabled: true,
    mms_enabled: false,
    is_active: true,
  },
  {
    id: "phone-2",
    workspace_id: WORKSPACE_ID,
    phone_number: "+15553334444",
    friendly_name: "Sales",
    sms_enabled: true,
    voice_enabled: false,
    mms_enabled: false,
    is_active: true,
  },
];

export default function NewSMSCampaignPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Fetch offers from API (with fallback to empty array)
  const { data: offersData, isLoading: offersLoading } = useQuery({
    queryKey: ["offers", WORKSPACE_ID],
    queryFn: async () => {
      try {
        const response = await offersApi.list(WORKSPACE_ID);
        return response.items;
      } catch {
        // Return empty array if API not available yet
        return [];
      }
    },
  });

  // Fetch phone numbers from API (with fallback to mock data)
  const { data: phoneNumbersData, isLoading: phoneNumbersLoading } = useQuery({
    queryKey: ["phone-numbers", WORKSPACE_ID],
    queryFn: async () => {
      try {
        const response = await phoneNumbersApi.list(WORKSPACE_ID, { sms_enabled: true });
        return response.items;
      } catch {
        // Use mock data if API not available yet
        return mockPhoneNumbers;
      }
    },
  });

  // Create offer mutation
  const createOfferMutation = useMutation({
    mutationFn: async (offer: Partial<Offer>) => {
      await offersApi.create(WORKSPACE_ID, {
        name: offer.name!,
        description: offer.description,
        discount_type: offer.discount_type!,
        discount_value: offer.discount_value!,
        terms: offer.terms,
        is_active: offer.is_active ?? true,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["offers", WORKSPACE_ID] });
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
      // Create the campaign
      const campaign = await smsCampaignsApi.create(WORKSPACE_ID, data);

      // Add contacts to the campaign
      if (contactIds.length > 0) {
        await smsCampaignsApi.addContacts(WORKSPACE_ID, campaign.id, contactIds);
      }

      return campaign;
    },
    onSuccess: (campaign) => {
      toast.success("Campaign created successfully!");
      queryClient.invalidateQueries({ queryKey: ["campaigns", WORKSPACE_ID] });
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

  const isLoading = offersLoading || phoneNumbersLoading;

  // Use mock data for contacts and agents (replace with API calls later)
  const contacts = mockContacts;
  const agents = mockAgents;
  const offers = offersData || [];
  const phoneNumbers = phoneNumbersData || mockPhoneNumbers;

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
