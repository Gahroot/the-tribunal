"use client";

import { BookOpen } from "lucide-react";
import { useState } from "react";

import { KnowledgeBaseTab } from "@/components/agents/tabs";
import { AppSidebar } from "@/components/layout/app-sidebar";
import {
  PageEmptyState,
  PageErrorState,
  PageLoadingState,
} from "@/components/ui/page-state";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAgents } from "@/hooks/useAgents";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";

export function KnowledgeBasePage() {
  const workspaceId = useWorkspaceId();
  const { data, isPending, error, refetch } = useAgents(workspaceId ?? "");
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);

  const agents = data?.items ?? [];
  const activeAgentId = selectedAgentId ?? agents[0]?.id ?? null;

  return (
    <AppSidebar>
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
              <BookOpen className="size-6" />
              Knowledge Base
            </h1>
            <p className="text-muted-foreground">
              Manage the documents your AI agents use to answer questions
              on-brand.
            </p>
          </div>
          {agents.length > 0 && activeAgentId && (
            <Select value={activeAgentId} onValueChange={setSelectedAgentId}>
              <SelectTrigger className="w-56">
                <SelectValue placeholder="Select an agent" />
              </SelectTrigger>
              <SelectContent>
                {agents.map((agent) => (
                  <SelectItem key={agent.id} value={agent.id}>
                    {agent.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        {!workspaceId || isPending ? (
          <PageLoadingState message="Loading agents…" />
        ) : error ? (
          <PageErrorState
            message="Failed to load agents."
            onRetry={() => refetch()}
          />
        ) : agents.length === 0 || !activeAgentId ? (
          <PageEmptyState
            icon={<BookOpen className="size-8" />}
            title="No agents yet"
            description="Create an AI agent first, then add knowledge documents it can draw from."
          />
        ) : (
          <KnowledgeBaseTab agentId={activeAgentId} />
        )}
      </div>
    </AppSidebar>
  );
}
