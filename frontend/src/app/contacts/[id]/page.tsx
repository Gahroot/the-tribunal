"use client";

import * as React from "react";
import { use } from "react";
import { useRouter } from "next/navigation";
import { ConversationLayout } from "@/components/layout/conversation-layout";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { useContactStore } from "@/lib/contact-store";
import { useContact } from "@/hooks/useContacts";
import { useWorkspaceId } from "@/hooks/use-workspace-id";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function ConversationPage({ params }: PageProps) {
  const { id } = use(params);
  const router = useRouter();
  const workspaceId = useWorkspaceId();
  const { setSelectedContact } = useContactStore();

  const contactId = parseInt(id, 10);

  // Fetch the specific contact
  const { data: contact, isLoading: isLoadingContact } = useContact(
    workspaceId ?? "",
    contactId,
  );

  // Set selected contact when loaded; redirect if not found
  React.useEffect(() => {
    if (contact) {
      setSelectedContact(contact);
    } else if (!isLoadingContact && !contact) {
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
