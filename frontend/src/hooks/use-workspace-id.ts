"use client";

import { useWorkspace } from "@/providers/workspace-provider";

export function useWorkspaceId(): string | null {
  const { currentWorkspaceId } = useWorkspace();
  return currentWorkspaceId;
}
