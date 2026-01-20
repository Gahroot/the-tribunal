"use client";

import { AppSidebar } from "@/components/layout/app-sidebar";
import { FindLeadsPage } from "@/components/contacts/find-leads-page";
import { useWorkspaceId } from "@/hooks/use-workspace-id";

export default function FindLeads() {
  const workspaceId = useWorkspaceId();

  return (
    <AppSidebar>
      <FindLeadsPage key={workspaceId} />
    </AppSidebar>
  );
}
