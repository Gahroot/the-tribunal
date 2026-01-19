"use client";

import { AppSidebar } from "@/components/layout/app-sidebar";
import { CampaignsList } from "@/components/campaigns/campaigns-list";
import { useWorkspaceId } from "@/hooks/use-workspace-id";

export default function CampaignsPage() {
  const workspaceId = useWorkspaceId();

  return (
    <AppSidebar>
      {/* Key prop forces remount when workspace changes, resetting all local state */}
      <CampaignsList key={workspaceId} />
    </AppSidebar>
  );
}
