"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { DateSeparator } from "@/components/conversation/date-separator";
import { MessageComposer } from "@/components/conversation/message-composer";
import { MessageItem } from "@/components/conversation/message-item";
import { Badge } from "@/components/ui/badge";
import { PageEmptyState, PageErrorState } from "@/components/ui/page-state";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { conversationsApi } from "@/lib/api/conversations";
import { messages } from "@/lib/messages";
import { queryKeys } from "@/lib/query-keys";
import { REALTIME } from "@/lib/query-options";
import { cn } from "@/lib/utils";
import { isSameDay } from "@/lib/utils/date";
import { getApiErrorMessage } from "@/lib/utils/errors";
import { formatPhoneNumber } from "@/lib/utils/phone";
import type { Conversation, Message, TimelineItem } from "@/types";

interface ContactlessThreadProps {
  workspaceId: string;
  conversation: Conversation;
  className?: string;
}

/** Adapt a stored message to the timeline shape the message renderers expect. */
function toTimelineItem(message: Message): TimelineItem {
  const isCall = message.channel === "voice" || message.channel === "voicemail";
  return {
    id: message.id,
    type: isCall ? "call" : message.channel === "email" ? "email" : "sms",
    timestamp: message.created_at,
    direction: message.direction,
    is_ai: message.is_ai,
    content: message.body || message.transcript || "",
    duration_seconds: message.duration_seconds,
    recording_url: message.recording_url,
    transcript: message.transcript,
    status: message.status,
    original_id: message.id,
    original_type: isCall ? "call_record" : "sms_message",
  };
}

/**
 * Fallback thread for conversations that have no linked contact yet (inbound
 * relay threads). Reuses the shared MessageItem / MessageComposer so the reply
 * and AI-draft flows behave exactly like the contact-linked feed.
 */
export function ContactlessThread({
  workspaceId,
  conversation,
  className,
}: ContactlessThreadProps) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isDrafting, setIsDrafting] = useState(false);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  const {
    data,
    isPending,
    isError,
    refetch,
  } = useQuery({
    queryKey: queryKeys.conversations.messages(workspaceId, conversation.id),
    queryFn: () => conversationsApi.getMessages(workspaceId, conversation.id),
    enabled: !!workspaceId && !!conversation.id,
    ...REALTIME,
    refetchIntervalInBackground: false,
  });

  const items = useMemo(() => (data ?? []).map(toTimelineItem), [data]);

  const groupedItems = useMemo(() => {
    type ItemGroup = { date: Date; items: typeof items };
    const groups: ItemGroup[] = [];
    items.forEach((item) => {
      const itemDate = new Date(item.timestamp);
      const lastGroup = groups[groups.length - 1];
      if (lastGroup && isSameDay(lastGroup.date, itemDate)) {
        lastGroup.items.push(item);
      } else {
        groups.push({ date: itemDate, items: [item] });
      }
    });
    return groups;
  }, [items]);

  // Auto-scroll to the newest message on load and on updates.
  useEffect(() => {
    if (scrollAreaRef.current) {
      const scrollContainer = scrollAreaRef.current.querySelector(
        "[data-radix-scroll-area-viewport]",
      );
      if (scrollContainer) {
        scrollContainer.scrollTop = scrollContainer.scrollHeight;
      }
    }
  }, [items]);

  const handleSend = async () => {
    const body = message.trim();
    if (!body || isSending) return;

    setIsSending(true);
    try {
      await conversationsApi.sendMessage(workspaceId, conversation.id, body);
      setMessage("");
      toast.success(messages.conversations.sent);
      void queryClient.invalidateQueries({
        queryKey: queryKeys.conversations.messages(workspaceId, conversation.id),
      });
      // Refresh the inbox list: preview + unread counts update in place.
      void queryClient.invalidateQueries({
        queryKey: queryKeys.conversations.all(workspaceId),
      });
    } catch (error) {
      toast.error(getApiErrorMessage(error, messages.conversations.sendFailed));
    } finally {
      setIsSending(false);
    }
  };

  const handleGenerateDraft = async () => {
    if (isDrafting) return;
    setIsDrafting(true);
    try {
      const result = await conversationsApi.generateFollowup(
        workspaceId,
        conversation.id,
      );
      setMessage(result.message);
      toast.success(messages.conversations.aiDraftInserted);
    } catch (error) {
      toast.error(
        getApiErrorMessage(error, messages.conversations.aiDraftFailed),
      );
    } finally {
      setIsDrafting(false);
    }
  };

  return (
    <div className={cn("flex h-full min-h-0 flex-col overflow-hidden", className)}>
      <div className="flex shrink-0 items-center justify-between gap-3 border-b px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <h2 className="truncate font-semibold">
            {formatPhoneNumber(conversation.contact_phone) ||
              conversation.contact_phone ||
              "Unknown number"}
          </h2>
          <span className="shrink-0 text-sm capitalize text-muted-foreground">
            {conversation.channel}
          </span>
        </div>
        <Badge
          variant={conversation.ai_enabled ? "default" : "secondary"}
          className="shrink-0"
        >
          {conversation.ai_enabled ? "AI on" : "AI off"}
        </Badge>
      </div>

      {isPending ? (
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          <Skeleton className="h-16 w-2/3 rounded-2xl" />
          <Skeleton className="ml-auto h-16 w-1/2 rounded-2xl" />
          <Skeleton className="h-16 w-3/5 rounded-2xl" />
        </div>
      ) : isError ? (
        <PageErrorState
          className="min-h-0 flex-1"
          message="We couldn't load this conversation. Please try again."
          onRetry={() => void refetch()}
        />
      ) : items.length === 0 ? (
        <PageEmptyState
          className="min-h-0 flex-1"
          title="No messages yet"
          description="Replies will appear here — send the first message below."
        />
      ) : (
        <ScrollArea ref={scrollAreaRef} className="min-h-0 flex-1">
          <div className="space-y-4 py-4">
            {groupedItems.map((group) => (
              <div key={group.date.toISOString()}>
                <DateSeparator date={group.date} />
                {group.items.map((item) => (
                  <MessageItem key={item.id} item={item} />
                ))}
              </div>
            ))}
          </div>
        </ScrollArea>
      )}

      <MessageComposer
        message={message}
        onMessageChange={setMessage}
        onSend={() => void handleSend()}
        isSending={isSending}
        phoneNumbers={[]}
        selectedFromNumber={undefined}
        onFromNumberChange={() => undefined}
        onGenerateDraft={() => void handleGenerateDraft()}
        isGeneratingDraft={isDrafting}
        draftDisabled={false}
      />
    </div>
  );
}
