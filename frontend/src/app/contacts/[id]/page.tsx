"use client";

import { useRouter } from "next/navigation";
import { use, useEffect } from "react";

import { AppSidebar } from "@/components/layout/app-sidebar";
import { ConversationLayout } from "@/components/layout/conversation-layout";
import { useContact } from "@/hooks/useContacts";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { useContactStore } from "@/lib/contact-store";

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
  const { data: contact, isPending: isLoadingContact } = useContact(
    workspaceId ?? "",
    contactId,
  );

  // Set selected contact when loaded; redirect if not found
  useEffect(() => {
    if (workspaceId && contact && (!contact.workspace_id || contact.workspace_id === workspaceId)) {
      setSelectedContact(contact);
    } else if (!isLoadingContact && !contact) {
      router.push("/");
    }
  }, [contact, isLoadingContact, workspaceId, setSelectedContact, router]);

  return (
    <AppSidebar>
      <div className="h-full overflow-hidden">
        {contact &&
        workspaceId &&
        (!contact.workspace_id || contact.workspace_id === workspaceId) ? (
          <ConversationLayout key={`${workspaceId}:${contactId}`} className="h-full" />
        ) : null}
      </div>
    </AppSidebar>
  );
}
