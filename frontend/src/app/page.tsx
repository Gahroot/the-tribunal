"use client";

import * as React from "react";
import { ContactsPage } from "@/components/contacts/contacts-page";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { useContactStore } from "@/lib/contact-store";
import { useContacts } from "@/hooks/useContacts";
import { useAuth } from "@/providers/auth-provider";

export default function Home() {
  const { workspaceId } = useAuth();
  const { setContacts, setIsLoadingContacts } = useContactStore();

  // Fetch contacts from API
  const { data, isLoading } = useContacts(workspaceId ?? "", {});

  // Sync API data to Zustand store
  React.useEffect(() => {
    setIsLoadingContacts(isLoading);
  }, [isLoading, setIsLoadingContacts]);

  React.useEffect(() => {
    if (data?.items) {
      setContacts(data.items);
    }
  }, [data, setContacts]);

  return (
    <AppSidebar>
      <div className="h-full overflow-hidden">
        <ContactsPage />
      </div>
    </AppSidebar>
  );
}
