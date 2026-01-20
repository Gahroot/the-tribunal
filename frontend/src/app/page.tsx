"use client";

import * as React from "react";
import { ContactsPage } from "@/components/contacts/contacts-page";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { useContactStore } from "@/lib/contact-store";
import { useAllContacts } from "@/hooks/useContacts";
import { useWorkspaceId } from "@/hooks/use-workspace-id";

export default function Home() {
  const workspaceId = useWorkspaceId();
  const { setContacts, setIsLoadingContacts, sortBy } = useContactStore();

  // Fetch ALL contacts from API (handles pagination automatically)
  const { data, isLoading } = useAllContacts(workspaceId ?? "", { sort_by: sortBy });

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
