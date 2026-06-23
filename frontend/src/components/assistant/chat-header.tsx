"use client";

import { Plus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { AssistantConversationMetaResponse } from "@/lib/api/assistant";
import type { ConversationRuntime } from "@/lib/assistant/conversation-runtime";

export function ChatHeader({
  conversation,
  runtime,
  onNewConversation,
}: {
  conversation?: AssistantConversationMetaResponse;
  runtime: ConversationRuntime;
  onNewConversation: () => void;
}) {
  return (
    <div className="flex items-center justify-between border-b px-4 py-3 lg:px-6">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <h2 className="truncate text-sm font-semibold">
            {conversation?.title ?? "New assistant chat"}
          </h2>
          {runtime.isStreaming ? (
            <Badge variant="secondary" className="gap-1">
              <span className="size-1.5 rounded-full bg-primary" />
              Streaming
            </Badge>
          ) : null}
        </div>
        <p className="text-xs text-muted-foreground">
          {runtime.isStreaming ? "Working live…" : "Each chat keeps its own CRM context."}
        </p>
      </div>
      <Button type="button" variant="outline" size="sm" onClick={onNewConversation}>
        <Plus className="mr-1 size-3.5" />
        New chat
      </Button>
    </div>
  );
}
