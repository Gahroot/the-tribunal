"use client";

import { useAuth } from "@/providers/auth-provider";

export function useWorkspaceId(): string {
  const { workspaceId } = useAuth();
  if (!workspaceId) {
    throw new Error("useWorkspaceId must be used within a workspace context");
  }
  return workspaceId;
}
