"use client";

import * as React from "react";
import { use } from "react";
import { useRouter } from "next/navigation";
import { ConversationLayout } from "@/components/layout/conversation-layout";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { useContactStore } from "@/lib/contact-store";
import { useAllContacts, useContact, useContactTimeline } from "@/hooks/useContacts";
import { useAuth } from "@/providers/auth-provider";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function ConversationPage({ params }: PageProps) {
  const { id } = use(params);
  const router = useRouter();
  const { workspaceId } = useAuth();
  const {
    setContacts,
    setSelectedContact,
    setTimeline,
    setIsLoadingContacts,
    setIsLoadingTimeline,
  } = useContactStore();

  const contactId = parseInt(id, 10);

  // Fetch ALL contacts (handles pagination automatically)
  const { data: contactsData, isLoading: isLoadingContactsList } = useAllContacts(
    workspaceId ?? "",
    {},
  );

  // Fetch the specific contact
  const { data: contact, isLoading: isLoadingContact } = useContact(
    workspaceId ?? "",
    contactId,
  );

  // Fetch the timeline for this contact
  const { data: timelineData, isLoading: isLoadingTimelineData } = useContactTimeline(
    workspaceId ?? "",
    contactId,
  );

  // Sync contacts list to store
  React.useEffect(() => {
    setIsLoadingContacts(isLoadingContactsList);
  }, [isLoadingContactsList, setIsLoadingContacts]);

  React.useEffect(() => {
    if (contactsData?.items) {
      setContacts(contactsData.items);
    }
  }, [contactsData, setContacts]);

  // Set loading state for timeline
  React.useEffect(() => {
    setIsLoadingTimeline(isLoadingTimelineData);
  }, [isLoadingTimelineData, setIsLoadingTimeline]);

  // Set timeline data when loaded
  React.useEffect(() => {
    if (timelineData) {
      setTimeline(timelineData);
    }
  }, [timelineData, setTimeline]);

  // Set selected contact when loaded
  React.useEffect(() => {
    if (contact) {
      setSelectedContact(contact);
    } else if (!isLoadingContact && !contact && workspaceId) {
      // Contact not found, redirect to contacts page
      router.push("/");
    }
  }, [contact, isLoadingContact, workspaceId, setSelectedContact, router]);

  return (
    <AppSidebar>
      <div className="h-full overflow-hidden">
        <ConversationLayout className="h-full" />
      </div>
    </AppSidebar>
  );
}
