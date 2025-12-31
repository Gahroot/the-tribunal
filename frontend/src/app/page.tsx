"use client";

import * as React from "react";
import { ContactsPage } from "@/components/contacts/contacts-page";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { useContactStore } from "@/lib/contact-store";
import { mockContacts, mockAgents, mockAutomations, mockContactAgents } from "@/lib/mock-data";

export default function Home() {
  const { setContacts, setAgents, setAutomations, setContactAgents, setIsLoadingContacts } = useContactStore();

  // Load mock data on mount
  React.useEffect(() => {
    setIsLoadingContacts(true);
    // Simulate API delay
    setTimeout(() => {
      setContacts(mockContacts);
      setAgents(mockAgents);
      setAutomations(mockAutomations);
      setContactAgents(mockContactAgents);
      setIsLoadingContacts(false);
    }, 500);
  }, [setContacts, setAgents, setAutomations, setContactAgents, setIsLoadingContacts]);

  return (
    <AppSidebar>
      <div className="h-full overflow-hidden">
        <ContactsPage />
      </div>
    </AppSidebar>
  );
}
