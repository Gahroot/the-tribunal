"use client";

import { useWorkspace } from "@/providers/workspace-provider";

export function useWorkspaceId(): string {
  const { currentWorkspaceId } = useWorkspace();
  if (!currentWorkspaceId) {
    throw new Error("useWorkspaceId must be used within a workspace context");
  }
  return currentWorkspaceId;
}
