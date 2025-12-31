"use client";

import * as React from "react";
import { use } from "react";
import { useRouter } from "next/navigation";
import { ConversationLayout } from "@/components/layout/conversation-layout";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { useContactStore } from "@/lib/contact-store";
import { getMockTimeline, mockContacts, mockAgents, mockAutomations, mockContactAgents } from "@/lib/mock-data";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function ConversationPage({ params }: PageProps) {
  const { id } = use(params);
  const router = useRouter();
  const {
    contacts,
    setContacts,
    setSelectedContact,
    setTimeline,
    setIsLoadingContacts,
    setIsLoadingTimeline,
    setAgents,
    setAutomations,
    setContactAgents,
  } = useContactStore();

  const contactId = parseInt(id, 10);

  // Load contacts if not already loaded
  React.useEffect(() => {
    if (contacts.length === 0) {
      setIsLoadingContacts(true);
      setTimeout(() => {
        setContacts(mockContacts);
        setAgents(mockAgents);
        setAutomations(mockAutomations);
        setContactAgents(mockContactAgents);
        setIsLoadingContacts(false);
      }, 300);
    } else {
      // Ensure agents and automations are loaded
      setAgents(mockAgents);
      setAutomations(mockAutomations);
      setContactAgents(mockContactAgents);
    }
  }, [contacts.length, setContacts, setAgents, setAutomations, setContactAgents, setIsLoadingContacts]);

  // Set selected contact and load timeline when contacts are available
  React.useEffect(() => {
    if (contacts.length > 0) {
      const contact = contacts.find((c) => c.id === contactId);
      if (contact) {
        setSelectedContact(contact);
        setIsLoadingTimeline(true);
        setTimeout(() => {
          const timeline = getMockTimeline(contactId);
          setTimeline(timeline);
          setIsLoadingTimeline(false);
        }, 200);
      } else {
        // Contact not found, redirect to contacts page
        router.push("/");
      }
    }
  }, [contacts, contactId, setSelectedContact, setTimeline, setIsLoadingTimeline, router]);

  return (
    <AppSidebar>
      <div className="h-full overflow-hidden">
        <ConversationLayout className="h-full" />
      </div>
    </AppSidebar>
  );
}
