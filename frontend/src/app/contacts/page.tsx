"use client";

import * as React from "react";
import { ContactsPage } from "@/components/contacts/contacts-page";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { useContactStore } from "@/lib/contact-store";
import { useContactsPaginated } from "@/hooks/useContacts";
import { useWorkspaceId } from "@/hooks/use-workspace-id";
import type { ContactStatus } from "@/types";
import type { ContactsListParams } from "@/lib/api/contacts";

export default function Home() {
  const workspaceId = useWorkspaceId();
  const {
    setContacts,
    setIsLoadingContacts,
    searchQuery,
    statusFilter,
    sortBy,
    filters,
    contactsPage,
    contactsPageSize,
    setPaginationMeta,
  } = useContactStore();

  const params: ContactsListParams = {
    page: contactsPage,
    page_size: contactsPageSize,
    sort_by: sortBy,
    ...(searchQuery.trim() && { search: searchQuery.trim() }),
    ...(statusFilter && { status: statusFilter as ContactStatus }),
    ...(filters && { filters: JSON.stringify(filters) }),
  };

  const { data, isLoading } = useContactsPaginated(workspaceId ?? "", params);

  React.useEffect(() => {
    setIsLoadingContacts(isLoading);
  }, [isLoading, setIsLoadingContacts]);

  React.useEffect(() => {
    if (data) {
      setContacts(data.items);
      setPaginationMeta({ total: data.total, pages: data.pages });
    }
  }, [data, setContacts, setPaginationMeta]);

  return (
    <AppSidebar>
      <div className="h-full overflow-hidden">
        <React.Suspense fallback={null}>
          <ContactsPage />
        </React.Suspense>
      </div>
    </AppSidebar>
  );
}
