"use client";

import { AlertCircle, Send, Square } from "lucide-react";

import {
  ChatHeader,
  ConversationSidebar,
  EmptyState,
  MessageBubble,
  StreamingBubble,
} from "@/components/assistant/assistant-chat-views";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { useAssistantChat } from "@/hooks/useAssistantChat";
import { cn } from "@/lib/utils";

export function AssistantChat({ className }: { className?: string }) {
  const {
    workspaceId,
    conversations,
    conversationsLoading,
    activeConversation,
    resolvedActiveConversationId,
    runtimes,
    activeRuntime,
    visibleMessages,
    input,
    setInput,
    scrollRef,
    handleNewConversation,
    handleSelectConversation,
    handleDeleteConversation,
    sendMessage,
    handleSubmit,
    handleKeyDown,
    handleStop,
  } = useAssistantChat();

  return (
    <div className={cn("flex h-full min-h-0 overflow-hidden", className)}>
      <ConversationSidebar
        conversations={conversations}
        activeConversationId={resolvedActiveConversationId}
        runtimes={runtimes}
        isLoading={conversationsLoading}
        onNewConversation={handleNewConversation}
        onSelectConversation={handleSelectConversation}
        onDeleteConversation={handleDeleteConversation}
      />

      <section className="flex min-w-0 flex-1 flex-col bg-background">
        <ChatHeader
          conversation={activeConversation}
          runtime={activeRuntime}
          onNewConversation={handleNewConversation}
        />

        <ScrollArea className="min-h-0 flex-1">
          <div ref={scrollRef} className="space-y-4 p-4 lg:p-6">
            {visibleMessages.length === 0 && !activeRuntime.isStreaming ? (
              <EmptyState onPrompt={sendMessage} />
            ) : null}

            {visibleMessages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}

            {activeRuntime.isStreaming ? <StreamingBubble runtime={activeRuntime} /> : null}

            {activeRuntime.error ? (
              <div className="flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                <AlertCircle className="size-4" />
                {activeRuntime.error}
              </div>
            ) : null}
          </div>
        </ScrollArea>

        <form onSubmit={handleSubmit} className="border-t bg-background/95 p-4">
          <div className="flex items-end gap-2">
            <Textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Ask your CRM assistant…"
              className="max-h-[140px] min-h-[48px] resize-none"
              rows={1}
              onKeyDown={handleKeyDown}
              disabled={!workspaceId}
            />
            {activeRuntime.isStreaming ? (
              <Button type="button" size="icon" variant="secondary" onClick={handleStop}>
                <Square className="size-4" />
                <span className="sr-only">Stop streaming</span>
              </Button>
            ) : (
              <Button
                type="submit"
                size="icon"
                disabled={!input.trim() || !workspaceId}
                aria-label="Send message"
              >
                <Send className="size-4" />
              </Button>
            )}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            Press Enter to send, Shift+Enter for a new line.
          </p>
        </form>
      </section>
    </div>
  );
}
