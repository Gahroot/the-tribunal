"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquare } from "lucide-react";
import { AnimatePresence } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { InboxThread, type InboxThreadProps } from "@/components/conversation/inbox-thread";
import { PageEmptyState, PageErrorState } from "@/components/ui/page-state";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { useAgents } from "@/hooks/useAgents";
import {
  useContactTimeline,
  useToggleContactAI,
  useAssignContactAgent,
} from "@/hooks/useContacts";
import { useClearConversationHistory } from "@/hooks/useConversations";
import { usePhoneNumbers } from "@/hooks/usePhoneNumbers";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { conversationsApi } from "@/lib/api/conversations";
import { useContactStore } from "@/lib/contact-store";
import { messages } from "@/lib/messages";
import { queryKeys } from "@/lib/query-keys";
import { cn } from "@/lib/utils";
import { isSameDay } from "@/lib/utils/date";
import { getApiErrorMessage } from "@/lib/utils/errors";
import { normalizePhoneForComparison } from "@/lib/utils/phone";
import type { Contact, Conversation } from "@/types";

import { ChatHeader } from "./chat-header";
import { DateSeparator } from "./date-separator";
import { MessageComposer } from "./message-composer";
import { MessageItem } from "./message-item";

interface ConversationFeedProps {
  className?: string;
  /**
   * Contact to render. Overrides the zustand store selection so the inbox can
   * drive thread switching with plain React state (reflow, not reload).
   * Omit to keep the store-driven behavior used by other pages.
   */
  contact?: Contact | null;
  /** Show the AI-draft control in the composer (generate → fill → review → send). */
  enableAIDraft?: boolean;
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4 p-4">
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className={cn(
            "flex gap-3",
            i % 2 === 0 ? "flex-row" : "flex-row-reverse",
          )}
        >
          <Skeleton className="h-8 w-8 rounded-full shrink-0" />
          <Skeleton
            className={cn("h-16 rounded-2xl", i % 2 === 0 ? "w-48" : "w-64")}
          />
        </div>
      ))}
    </div>
  );
}

export function ConversationFeed(props: ConversationFeedProps | InboxThreadProps) {
  // The inbox owns an exact thread. Contact pages retain their unified timeline.
  if ("conversation" in props) return <InboxThread {...props} />;
  return <ContactConversationFeed {...props} />;
}

function ContactConversationFeed({
  className,
  contact,
  enableAIDraft,
}: ConversationFeedProps) {
  const { selectedContact: storeSelectedContact } = useContactStore();
  const selectedContact = contact ?? storeSelectedContact;
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();

  // Fetch timeline via React Query (polls every 3s)
  const {
    data: timelineData,
    isPending: isLoadingTimeline,
    isError: isTimelineError,
    refetch: refetchTimeline,
  } = useContactTimeline(
    workspaceId ?? "",
    selectedContact?.id ?? 0,
  );
  const timeline = useMemo(() => timelineData ?? [], [timelineData]);
  const [message, setMessage] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [selectedFromNumber, setSelectedFromNumber] = useState<
    string | undefined
  >();
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  // Fetch phone numbers for the workspace
  const { data: phoneNumbersData } = usePhoneNumbers(workspaceId ?? "", {
    sms_enabled: true,
    active_only: true,
  });
  const phoneNumbers = useMemo(
    () => phoneNumbersData?.items ?? [],
    [phoneNumbersData?.items],
  );
  const fallbackFromNumber = phoneNumbers[0]?.phone_number;
  const activeFromNumber = selectedFromNumber ?? fallbackFromNumber;

  // Fetch agents for the workspace
  const { data: agentsData } = useAgents(workspaceId ?? "");
  const agents = useMemo(
    () => agentsData?.items ?? [],
    [agentsData?.items],
  );

  // Fetch conversations to find the one for the current contact
  const { data: conversationsData } = useQuery({
    queryKey: queryKeys.conversations.byContact(
      workspaceId ?? "",
      selectedContact?.id,
    ),
    queryFn: () =>
      workspaceId
        ? conversationsApi.list(workspaceId, { page: 1, page_size: 100 })
        : Promise.resolve({
            items: [],
            total: 0,
            page: 1,
            page_size: 100,
            pages: 0,
          }),
    enabled: !!workspaceId && !!selectedContact,
  });

  const selectedContactPhone = normalizePhoneForComparison(
    selectedContact?.phone_number,
  );

  // Find the conversation for the current contact. Inbound relay threads may
  // arrive before the contact_id is linked, so fall back to normalized phone.
  const contactConversation: Conversation | undefined =
    conversationsData?.items?.find((conv) => {
      if (conv.contact_id === selectedContact?.id) return true;
      return (
        !!selectedContactPhone &&
        normalizePhoneForComparison(conv.contact_phone) === selectedContactPhone
      );
    });

  // Mutations for AI toggle, agent assignment, and clear history.
  // Toggle/assign use the contact-level endpoints, which find-or-create the
  // conversation server-side — so they work even before the first message.
  const toggleAIMutation = useToggleContactAI(workspaceId ?? "");
  const assignAgentMutation = useAssignContactAgent(workspaceId ?? "");
  const clearHistoryMutation = useClearConversationHistory(workspaceId ?? "");

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (scrollAreaRef.current) {
      const scrollContainer = scrollAreaRef.current.querySelector(
        "[data-radix-scroll-area-viewport]",
      );
      if (scrollContainer) {
        scrollContainer.scrollTop = scrollContainer.scrollHeight;
      }
    }
  }, [timeline]);

  // Group timeline items by date
  type TimelineGroup = { date: Date; items: typeof timeline };
  const groupedTimeline = useMemo(() => {
    const groups: TimelineGroup[] = [];

    timeline.forEach((item) => {
      const itemDate = new Date(item.timestamp);
      const lastGroup = groups[groups.length - 1];

      if (lastGroup && isSameDay(lastGroup.date, itemDate)) {
        lastGroup.items.push(item);
      } else {
        groups.push({ date: itemDate, items: [item] });
      }
    });

    return groups;
  }, [timeline]);

  // Fernand-style AI draft: generate → fill the composer → human review → send.
  const [isDrafting, setIsDrafting] = useState(false);

  const handleGenerateDraft = async () => {
    if (!workspaceId || !contactConversation || isDrafting) return;
    setIsDrafting(true);
    try {
      const result = await conversationsApi.generateFollowup(
        workspaceId,
        contactConversation.id,
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

  const handleSendMessage = async () => {
    if (!message.trim() || !selectedContact || !workspaceId || isSending) return;

    const messageBody = message.trim();
    setMessage("");
    setIsSending(true);

    try {
      await conversationsApi.sendMessageToContact(
        workspaceId,
        selectedContact.id,
        messageBody,
        activeFromNumber
      );

      // Invalidate timeline so the sent message appears immediately
      void queryClient.invalidateQueries({
        queryKey: queryKeys.contacts.timeline(
          workspaceId ?? "",
          selectedContact.id,
        ),
      });
      // Refresh the inbox list too: preview + counts update in place.
      void queryClient.invalidateQueries({
        queryKey: queryKeys.conversations.all(workspaceId),
      });
      toast.success(messages.conversations.sent);
    } catch (error) {
      // Restore the message if sending failed
      setMessage(messageBody);
      const errorMessage =
        error instanceof Error ? error.message : "Failed to send message";
      toast.error(errorMessage);
    } finally {
      setIsSending(false);
    }
  };

  const handleToggleAI = () => {
    if (!selectedContact) return;

    // Optimistic state already reflects the flip; derive the target from the
    // current conversation (defaults to enabling when no thread exists yet).
    const newState = !contactConversation?.ai_enabled;
    toggleAIMutation.mutate(
      { contactId: selectedContact.id, enabled: newState },
      {
        onSuccess: () => {
          toast.success(
            newState ? "AI engagement enabled" : "AI engagement disabled",
          );
        },
        onError: (err: unknown) => {
          toast.error(getApiErrorMessage(err, "Failed to toggle AI"));
        },
      },
    );
  };

  const handleAssignAgent = (agentId: string | null) => {
    if (!selectedContact) return;

    assignAgentMutation.mutate(
      { contactId: selectedContact.id, agentId },
      {
        onSuccess: () => {
          toast.success(agentId ? "Agent assigned" : "Agent unassigned");
        },
        onError: (err: unknown) => {
          toast.error(getApiErrorMessage(err, "Failed to assign agent"));
        },
      },
    );
  };

  const handleClearHistory = () => {
    if (!contactConversation) {
      toast.error("No conversation found for this contact");
      return;
    }

    clearHistoryMutation.mutate(contactConversation.id, {
      onSuccess: () => {
        void queryClient.invalidateQueries({
          queryKey: queryKeys.contacts.timeline(
            workspaceId ?? "",
            selectedContact?.id,
          ),
        });
        toast.success("Conversation history cleared");
      },
      onError: (err: unknown) => {
        toast.error(getApiErrorMessage(err, "Failed to clear history"));
      },
    });
  };

  const contactName = selectedContact
    ? [selectedContact.first_name, selectedContact.last_name]
        .filter(Boolean)
        .join(" ")
    : undefined;

  if (!selectedContact) {
    return (
      <PageEmptyState
        className={cn("h-full", className)}
        icon={<MessageSquare className="h-8 w-8" />}
        title="Select a contact"
        description="Choose a contact to view their conversation history"
      />
    );
  }

  return (
    <div className={cn("flex flex-col h-full overflow-hidden", className)}>
      <ChatHeader
        contactName={contactName}
        phoneNumber={selectedContact.phone_number}
        conversation={contactConversation}
        agents={agents}
        hasTimelineItems={timeline.length > 0}
        canManageAI={!!selectedContact?.phone_number}
        isToggleAIPending={toggleAIMutation.isPending}
        isAssignAgentPending={assignAgentMutation.isPending}
        isClearHistoryPending={clearHistoryMutation.isPending}
        onToggleAI={handleToggleAI}
        onAssignAgent={handleAssignAgent}
        onClearHistory={handleClearHistory}
      />

      {/* Messages */}
      <ScrollArea ref={scrollAreaRef} className="flex-1 min-h-0">
        {isLoadingTimeline ? (
          <LoadingSkeleton />
        ) : isTimelineError ? (
          <PageErrorState
            className="h-full"
            message="We couldn't load this conversation. Please try again."
            onRetry={() => refetchTimeline()}
          />
        ) : timeline.length === 0 ? (
          <PageEmptyState
            className="h-full"
            icon={<MessageSquare className="h-8 w-8" />}
            title="No conversation yet"
            description="Start a conversation by sending a message, making a call, or scheduling an appointment."
          />
        ) : (
          <div className="py-4">
            <AnimatePresence mode="popLayout">
              {groupedTimeline.map((group) => (
                <div key={group.date.toISOString()}>
                  <DateSeparator date={group.date} />
                  {group.items.map((item) => (
                    <MessageItem
                      key={item.id}
                      item={item}
                      contactName={contactName}
                    />
                  ))}
                </div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </ScrollArea>

      <MessageComposer
        message={message}
        onMessageChange={setMessage}
        onSend={handleSendMessage}
        isSending={isSending}
        phoneNumbers={phoneNumbers}
        selectedFromNumber={activeFromNumber}
        onFromNumberChange={setSelectedFromNumber}
        onGenerateDraft={enableAIDraft ? handleGenerateDraft : undefined}
        isGeneratingDraft={isDrafting}
        draftDisabled={!contactConversation}
      />
    </div>
  );
}
