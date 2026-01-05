"use client";

import * as React from "react";
import { OpportunitiesPage } from "@/components/opportunities/opportunities-page";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { useAuth } from "@/providers/auth-provider";

export default function Page() {
  const { workspaceId } = useAuth();

  if (!workspaceId) {
    return null;
  }

  return (
    <AppSidebar>
      <div className="h-full overflow-hidden">
        <OpportunitiesPage workspaceId={workspaceId} />
      </div>
    </AppSidebar>
  );
}
