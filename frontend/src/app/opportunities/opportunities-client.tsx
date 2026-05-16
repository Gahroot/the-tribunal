"use client";

import { OpportunitiesPage } from "@/components/opportunities/opportunities-page";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";

export function OpportunitiesClient() {
  const workspaceId = useWorkspaceId();
  return <OpportunitiesPage workspaceId={workspaceId ?? ""} />;
}
