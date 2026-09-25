"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { DateSeparator } from "@/components/conversation/date-separator";
import { MessageComposer } from "@/components/conversation/message-composer";
import { MessageItem } from "@/components/conversation/message-item";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageEmptyState, PageErrorState } from "@/components/ui/page-state";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { useToggleConversationAI } from "@/hooks/useConversations";
import { conversationsApi, type InboxConversation, type InboxMessage } from "@/lib/api/conversations";
import { messages } from "@/lib/messages";
import { queryKeys } from "@/lib/query-keys";
import { REALTIME } from "@/lib/query-options";
import { cn } from "@/lib/utils";
import { isSameDay } from "@/lib/utils/date";
import { getApiErrorMessage } from "@/lib/utils/errors";
import { formatPhoneNumber } from "@/lib/utils/phone";
import type { TimelineItem } from "@/types";

export interface InboxThreadProps {
  workspaceId: string;
  conversation: InboxConversation;
  draft: string;
  draftLimitReached?: boolean;
  onDraftChange: (value: string) => void;
  onViewed: (snapshot: InboxConversation) => Promise<void>;
  className?: string;
}

/** Adapt a stored message to the timeline shape the message renderers expect. */
function toTimelineItem(message: InboxMessage): TimelineItem {
  const isCall = message.channel === "voice" || message.channel === "voicemail";
  return {
    id: message.id,
    type: isCall ? "call" : message.channel === "email" ? "email" : "sms",
    timestamp: message.created_at,
    direction: message.direction === "inbound" || message.direction === "outbound" ? message.direction : undefined,
    is_ai: message.is_ai,
    content: message.body || message.transcript || "",
    duration_seconds: message.duration_seconds ?? undefined,
    recording_url: message.recording_url ?? undefined,
    transcript: message.transcript ?? undefined,
    status: message.status,
    original_id: message.id,
    original_type: isCall ? "call_record" : "sms_message",
  };
}

/**
 * Exact selected-thread renderer for both contact-linked and unknown numbers.
 * The contact page keeps its separate unified timeline; inbox actions never
 * infer a sender or thread from a contact-level first-page lookup.
 */
export function InboxThread({
  workspaceId,
  conversation,
  className,
  draft: message,
  draftLimitReached = false,
  onDraftChange,
  onViewed,
}: InboxThreadProps) {
  const queryClient = useQueryClient();
  const toggleAI = useToggleConversationAI(workspaceId, true);
  const revision = useRef(0);
  const sending = useRef(false);
  const draftRequest = useRef<AbortController | null>(null);
  const alive = useRef(true);
  const [sendError, setSendError] = useState<string | null>(null);
  const [draftError, setDraftError] = useState<string | null>(null);
  const setMessage = (value: string) => {
    revision.current += 1;
    onDraftChange(value);
  };
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      draftRequest.current?.abort();
    };
  }, []);
  const [isSending, setIsSending] = useState(false);
  const [isDrafting, setIsDrafting] = useState(false);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  const { data, isPending, isError, refetch } = useQuery({
    queryKey: queryKeys.conversations.messageSnapshot(
      workspaceId,
      conversation.id,
      conversation.last_message_at,
      conversation.unread_count,
    ),
    queryFn: ({ signal }) => conversationsApi.getMessages(workspaceId, conversation.id, signal),
    enabled: !!workspaceId && !!conversation.id,
    ...REALTIME,
    refetchIntervalInBackground: false,
    retry: 1,
    throwOnError: false,
  });

  useEffect(() => {
    if (!isPending && !isError && data) void onViewed(conversation);
  }, [data, isPending, isError, onViewed, conversation]);

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
    if (!body || sending.current || isPending || isError) return;

    sending.current = true;
    const sentRevision = revision.current;
    setIsSending(true);
    setSendError(null);
    draftRequest.current?.abort();
    try {
      const sent = await conversationsApi.sendMessage(workspaceId, conversation.id, body);
      if (sent.status === "failed")
        throw new Error("The message was not sent. Your draft is still here.");
      if (revision.current === sentRevision) onDraftChange("");
      toast.success(
        sent.status === "queued" || sent.status === "sending"
          ? "Message queued"
          : messages.conversations.sent,
      );
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.todayQueue(workspaceId) });
      if (conversation.contact_id)
        void queryClient.invalidateQueries({
          queryKey: queryKeys.contacts.timeline(workspaceId, conversation.contact_id),
        });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.conversations.messages(workspaceId, conversation.id),
      });
      // Refresh the inbox list: preview + unread counts update in place.
      void queryClient.invalidateQueries({
        queryKey: queryKeys.conversations.all(workspaceId),
      });
    } catch (error) {
      const text = getApiErrorMessage(error, messages.conversations.sendFailed);
      if (alive.current) setSendError(text);
      toast.error(text);
    } finally {
      sending.current = false;
      if (alive.current) setIsSending(false);
    }
  };

  const handleGenerateDraft = async () => {
    if (draftRequest.current || sending.current) return;
    if (message.trim() && !window.confirm("Replace your unsent text with an AI draft?")) return;
    const controller = new AbortController();
    draftRequest.current = controller;
    const startedRevision = revision.current;
    setIsDrafting(true);
    setDraftError(null);
    try {
      const result = await conversationsApi.generateFollowup(
        workspaceId,
        conversation.id,
        undefined,
        controller.signal,
      );
      if (controller.signal.aborted || !alive.current) return;
      if (revision.current !== startedRevision) {
        setDraftError("Your edits were kept. Generate again to replace them.");
        return;
      }
      setMessage(result.message);
      toast.success(messages.conversations.aiDraftInserted);
    } catch (error) {
      if (!controller.signal.aborted && alive.current)
        setDraftError(getApiErrorMessage(error, messages.conversations.aiDraftFailed));
    } finally {
      if (draftRequest.current === controller) draftRequest.current = null;
      if (alive.current) setIsDrafting(false);
    }
  };

  return (
    <div className={cn("flex h-full min-h-0 flex-col overflow-hidden", className)}>
      <div className="flex shrink-0 items-center justify-between gap-3 border-b px-4 py-3">
        <div className="min-w-0 text-sm">
          <span className="mr-2 uppercase text-muted-foreground">{conversation.channel}</span>
          <span className="block truncate sm:inline" title={conversation.workspace_phone}>
            From {formatPhoneNumber(conversation.workspace_phone) || conversation.workspace_phone}
          </span>
        </div>
        <Badge variant={conversation.ai_enabled ? "default" : "secondary"} className="shrink-0">
          {conversation.ai_paused ? "AI paused" : conversation.ai_enabled ? "AI on" : "AI off"}
        </Badge>
        <Button
          size="sm"
          variant="outline"
          disabled={toggleAI.isPending}
          onClick={() =>
            toggleAI.mutate(
              {
                conversationId: conversation.id,
                enabled: !conversation.ai_enabled || conversation.ai_paused,
              },
              { onError: () => toast.error("Couldn't change AI handling.") },
            )
          }
        >
          {!conversation.ai_enabled || conversation.ai_paused ? "Enable AI" : "Disable AI"}
        </Button>
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
          description="Replies appear here. Send the first message below."
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

      {data?.length === 100 ? (
        <p className="px-4 py-1 text-xs text-muted-foreground">
          Showing the 100 most recent messages.
        </p>
      ) : null}
      {sendError ? (
        <p role="alert" className="px-4 py-2 text-sm text-destructive">
          {sendError} Your draft is kept; review it before retrying.
        </p>
      ) : null}
      {draftError ? (
        <p role="alert" className="px-4 py-2 text-sm text-destructive">
          {draftError}
        </p>
      ) : null}
      {draftLimitReached ? <p role="status" className="px-4 py-2 text-sm">Send or discard an existing draft before starting another. Your 30 drafts are kept in this inbox.</p> : null}
      <MessageComposer
        textOnly
        disabled={isPending || isError || draftLimitReached}
        message={message}
        onMessageChange={setMessage}
        onSend={() => void handleSend()}
        isSending={isSending}
        phoneNumbers={[]}
        selectedFromNumber={undefined}
        onFromNumberChange={() => undefined}
        onGenerateDraft={() => void handleGenerateDraft()}
        isGeneratingDraft={isDrafting}
        draftDisabled={isPending || isError || isSending}
      />
    </div>
  );
}
