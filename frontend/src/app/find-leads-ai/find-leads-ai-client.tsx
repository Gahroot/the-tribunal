"use client";

import { FindLeadsAIPage } from "@/components/contacts/find-leads-ai-page";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";

export function FindLeadsAIClient() {
  const workspaceId = useWorkspaceId();
  return <FindLeadsAIPage key={workspaceId} />;
}
