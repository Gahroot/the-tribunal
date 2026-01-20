"use client";

import { AppSidebar } from "@/components/layout/app-sidebar";
import { ExperimentsList } from "@/components/experiments/experiments-list";
import { useWorkspaceId } from "@/hooks/use-workspace-id";

export default function ExperimentsPage() {
  const workspaceId = useWorkspaceId();

  return (
    <AppSidebar>
      {/* Key prop forces remount when workspace changes, resetting all local state */}
      <ExperimentsList key={workspaceId} />
    </AppSidebar>
  );
}
