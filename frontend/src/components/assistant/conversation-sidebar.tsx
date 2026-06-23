"use client";

import { Loader2, MessageSquare, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { AssistantConversationMetaResponse } from "@/lib/api/assistant";
import type { ConversationRuntime } from "@/lib/assistant/conversation-runtime";
import { cn } from "@/lib/utils";
import { formatTime } from "@/lib/utils/date";

export function ConversationSidebar({
  conversations,
  activeConversationId,
  runtimes,
  isLoading,
  onNewConversation,
  onSelectConversation,
  onDeleteConversation,
}: {
  conversations: AssistantConversationMetaResponse[];
  activeConversationId: string | null;
  runtimes: Record<string, ConversationRuntime>;
  isLoading: boolean;
  onNewConversation: () => void;
  onSelectConversation: (conversationId: string) => void;
  onDeleteConversation: (conversationId: string) => void;
}) {
  return (
    <aside className="hidden w-72 shrink-0 border-r bg-muted/20 md:flex md:flex-col">
      <div className="flex items-center justify-between border-b p-3">
        <div>
          <p className="text-sm font-medium">Chats</p>
          <p className="text-xs text-muted-foreground">Switch context anytime</p>
        </div>
        <Button size="sm" onClick={onNewConversation}>
          <Plus className="mr-1 size-3.5" />
          New
        </Button>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-1 p-2">
          {isLoading ? (
            <div className="flex items-center gap-2 px-2 py-4 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Loading chats…
            </div>
          ) : null}
          {conversations.map((conversation) => (
            <ConversationItem
              key={conversation.id}
              conversation={conversation}
              runtime={runtimes[conversation.id]}
              isActive={conversation.id === activeConversationId}
              onSelect={() => onSelectConversation(conversation.id)}
              onDelete={() => onDeleteConversation(conversation.id)}
            />
          ))}
          {!isLoading && conversations.length === 0 ? (
            <p className="px-2 py-4 text-sm text-muted-foreground">
              No saved assistant chats yet.
            </p>
          ) : null}
        </div>
      </ScrollArea>
    </aside>
  );
}

function ConversationItem({
  conversation,
  runtime,
  isActive,
  onSelect,
  onDelete,
}: {
  conversation: AssistantConversationMetaResponse;
  runtime?: ConversationRuntime;
  isActive: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      className={cn(
        "group flex items-start gap-2 rounded-lg px-2 py-2 text-left transition-colors",
        isActive ? "bg-background shadow-sm" : "hover:bg-background/70",
      )}
    >
      <button type="button" className="min-w-0 flex-1 text-left" onClick={onSelect}>
        <div className="flex items-center gap-2">
          <MessageSquare className="size-3.5 shrink-0 text-muted-foreground" />
          <p className="truncate text-sm font-medium">{conversation.title}</p>
          {runtime?.isStreaming ? (
            <span className="size-1.5 shrink-0 rounded-full bg-primary" />
          ) : null}
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {conversation.message_count} messages · {formatTime(conversation.updated_at)}
        </p>
      </button>
      <Button
        type="button"
        size="icon"
        variant="ghost"
        className="size-7 opacity-0 group-hover:opacity-100"
        onClick={onDelete}
      >
        <Trash2 className="size-3.5" />
        <span className="sr-only">Delete chat</span>
      </Button>
    </div>
  );
}
