"use client";

import { AppSidebar } from "@/components/layout/app-sidebar";
import { FindLeadsAIPage } from "@/components/contacts/find-leads-ai-page";
import { useWorkspaceId } from "@/hooks/use-workspace-id";

export default function FindLeadsAI() {
  const workspaceId = useWorkspaceId();

  return (
    <AppSidebar>
      <FindLeadsAIPage key={workspaceId} />
    </AppSidebar>
  );
}
