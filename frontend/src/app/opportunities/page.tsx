"use client";

import * as React from "react";
import { OpportunitiesPage } from "@/components/opportunities/opportunities-page";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { useWorkspaceId } from "@/hooks/use-workspace-id";

export default function Page() {
  const workspaceId = useWorkspaceId();

  return (
    <AppSidebar>
      <div className="h-full overflow-hidden">
        <OpportunitiesPage workspaceId={workspaceId ?? ""} />
      </div>
    </AppSidebar>
  );
}
