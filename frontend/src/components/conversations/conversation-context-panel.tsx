"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot } from "lucide-react";
import { useMemo } from "react";
import { toast } from "sonner";

import { ContactHeader } from "@/components/contacts/contact-sidebar/contact-header";
import { ContactInfoSection } from "@/components/contacts/contact-sidebar/contact-info-section";
import { Badge } from "@/components/ui/badge";
import { PageEmptyState } from "@/components/ui/page-state";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import { useAgents } from "@/hooks/useAgents";
import { useAssignContactAgent, useUpdateContact } from "@/hooks/useContacts";
import { useAssignAgent } from "@/hooks/useConversations";
import { opportunitiesApi } from "@/lib/api/opportunities";
import { messages } from "@/lib/messages";
import { queryKeys } from "@/lib/query-keys";
import { STATIC } from "@/lib/query-options";
import {
  contactStatusDotColors,
  contactStatusLabels,
  opportunityStatusDotColors,
} from "@/lib/status-colors";
import { cn } from "@/lib/utils";
import { getApiErrorMessage } from "@/lib/utils/errors";
import { formatCurrency } from "@/lib/utils/number";
import { formatPhoneNumber } from "@/lib/utils/phone";
import type {
  Contact,
  ContactStatus,
  Conversation,
  OpportunityStatus,
} from "@/types";

const CONTACT_STATUSES: ContactStatus[] = [
  "new",
  "contacted",
  "qualified",
  "converted",
  "lost",
];

const OPPORTUNITY_STATUSES: OpportunityStatus[] = [
  "open",
  "won",
  "lost",
  "abandoned",
];

interface ConversationContextPanelProps {
  workspaceId: string;
  contact: Contact | null;
  conversation: Conversation | null;
  className?: string;
}

/**
 * Column 3 of the inbox: contact details, opportunity state, and the active
 * agent with an assignment control. All updates land through React Query
 * invalidation so the list, thread header, and panel reflow in place.
 */
export function ConversationContextPanel({
  workspaceId,
  contact,
  conversation,
  className,
}: ConversationContextPanelProps) {
  const queryClient = useQueryClient();

  const { data: agentsData, isPending: isAgentsPending } = useAgents(workspaceId);
  const agents = useMemo(() => agentsData?.items ?? [], [agentsData?.items]);

  const updateContactMutation = useUpdateContact(workspaceId);
  const assignContactAgentMutation = useAssignContactAgent(workspaceId);
  const assignConversationAgentMutation = useAssignAgent(workspaceId);

  // The opportunities list has no contact filter, so fetch a page and filter
  // client-side by primary contact (v1 scale: one page of open deals is plenty
  // for the handful a single contact usually has).
  const { data: opportunitiesData, isPending: isOpportunitiesPending } =
    useQuery({
      queryKey: queryKeys.opportunities.list(workspaceId, {
        page: 1,
        page_size: 100,
      }),
      queryFn: () =>
        opportunitiesApi.list(workspaceId, { page: 1, page_size: 100 }),
      enabled: !!workspaceId && !!contact,
      ...STATIC,
    });

  const { data: pipelines } = useQuery({
    queryKey: queryKeys.opportunities.pipelines(workspaceId),
    queryFn: () => opportunitiesApi.listPipelines(workspaceId),
    enabled: !!workspaceId && !!contact,
    ...STATIC,
  });

  const stageNames = useMemo(() => {
    const map = new Map<string, string>();
    for (const pipeline of pipelines ?? []) {
      for (const stage of pipeline.stages ?? []) {
        map.set(stage.id, stage.name);
      }
    }
    return map;
  }, [pipelines]);

  const contactOpportunities = useMemo(
    () =>
      (opportunitiesData?.items ?? []).filter(
        (opportunity) => opportunity.primary_contact_id === contact?.id,
      ),
    [opportunitiesData?.items, contact?.id],
  );

  const updateOpportunityStatusMutation = useMutation({
    mutationFn: (variables: {
      opportunityId: string;
      status: OpportunityStatus;
    }) =>
      opportunitiesApi.update(workspaceId, variables.opportunityId, {
        status: variables.status,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.opportunities.all(workspaceId),
      });
      toast.success(messages.opportunities.statusUpdated);
    },
    onError: (error) => {
      toast.error(
        getApiErrorMessage(error, messages.opportunities.statusUpdateFailed),
      );
    },
  });

  const handleContactStatusChange = (value: string) => {
    if (!contact) return;
    updateContactMutation.mutate(
      { id: contact.id, data: { status: value as ContactStatus } },
      {
        onSuccess: () => toast.success(messages.contacts.updated),
        onError: (error) =>
          toast.error(getApiErrorMessage(error, messages.contacts.updateFailed)),
      },
    );
  };

  const handleAssignAgent = (value: string) => {
    const agentId = value === "none" ? null : value;
    const callbacks = {
      onSuccess: () =>
        toast.success(
          agentId
            ? messages.conversations.assigned
            : messages.conversations.unassigned,
        ),
      onError: (error: Error) =>
        toast.error(getApiErrorMessage(error, messages.conversations.assignFailed)),
    };

    if (contact) {
      assignContactAgentMutation.mutate(
        { contactId: contact.id, agentId },
        callbacks,
      );
    } else if (conversation) {
      assignConversationAgentMutation.mutate(
        { conversationId: conversation.id, agentId },
        callbacks,
      );
    }
  };

  const assignedAgentId = conversation?.assigned_agent_id ?? null;
  const assignedAgentName = assignedAgentId
    ? agents.find((agent) => agent.id === assignedAgentId)?.name ?? "Agent"
    : "No agent";

  return (
    <div
      className={cn(
        "flex h-full min-h-0 flex-col overflow-hidden bg-background",
        className,
      )}
    >
      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-4 p-4">
          {!contact && !conversation ? (
            <PageEmptyState
              className="min-h-[220px] p-6"
              title="No conversation selected"
              description="Choose a thread to see contact details, deal state, and the assigned agent."
            />
          ) : (
            <>
              {contact ? (
                <div className="space-y-4">
                  <ContactHeader contact={contact} />

                  <div className="space-y-1.5">
                    <p className="px-2 text-sm font-medium text-muted-foreground">
                      Status
                    </p>
                    <Select
                      value={contact.status}
                      onValueChange={handleContactStatusChange}
                      disabled={updateContactMutation.isPending}
                    >
                      <SelectTrigger className="w-full" aria-label="Contact status">
                        <SelectValue placeholder="Status" />
                      </SelectTrigger>
                      <SelectContent>
                        {CONTACT_STATUSES.map((status) => (
                          <SelectItem key={status} value={status}>
                            <span
                              aria-hidden
                              className={cn(
                                "h-2 w-2 rounded-full",
                                contactStatusDotColors[status],
                              )}
                            />
                            {contactStatusLabels[status]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <ContactInfoSection contact={contact} />
                </div>
              ) : conversation ? (
                <div className="space-y-2">
                  <h3 className="px-2 text-sm font-medium text-muted-foreground">
                    Conversation
                  </h3>
                  <div className="space-y-1 px-2">
                    <p className="text-sm font-medium">
                      {formatPhoneNumber(conversation.contact_phone) ||
                        conversation.contact_phone ||
                        "Unknown number"}
                    </p>
                    <p className="text-xs capitalize text-muted-foreground">
                      {conversation.channel} channel · {conversation.status}
                    </p>
                  </div>
                </div>
              ) : null}

              <Separator />

              <section
                aria-labelledby="inbox-context-opportunity"
                className="space-y-2"
              >
                <h3
                  id="inbox-context-opportunity"
                  className="px-2 text-sm font-medium text-muted-foreground"
                >
                  Opportunity
                </h3>
                {!contact ? (
                  <p className="px-2 text-sm text-muted-foreground">
                    No linked contact.
                  </p>
                ) : isOpportunitiesPending ? (
                  <div className="space-y-2 px-2">
                    <Skeleton className="h-14 w-full rounded-lg" />
                    <Skeleton className="h-14 w-full rounded-lg" />
                  </div>
                ) : contactOpportunities.length === 0 ? (
                  <p className="px-2 text-sm text-muted-foreground">
                    No opportunities linked to this contact.
                  </p>
                ) : (
                  contactOpportunities.map((opportunity) => {
                    const stageName = opportunity.stage_id
                      ? stageNames.get(opportunity.stage_id)
                      : undefined;
                    return (
                      <div
                        key={opportunity.id}
                        className="mx-2 space-y-2 rounded-lg border p-3"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-medium">
                              {opportunity.name}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {stageName ?? "No stage"} · {opportunity.probability}%
                            </p>
                          </div>
                          {typeof opportunity.amount === "number" ? (
                            <span className="shrink-0 text-sm font-medium tabular-nums">
                              {formatCurrency(
                                opportunity.amount,
                                opportunity.currency,
                              )}
                            </span>
                          ) : null}
                        </div>
                        <div className="flex items-center gap-2">
                          <StatusBadge
                            dotClass={opportunityStatusDotColors[opportunity.status]}
                            className="text-[10px] capitalize"
                          >
                            {opportunity.status}
                          </StatusBadge>
                          <Select
                            value={opportunity.status}
                            onValueChange={(value) =>
                              updateOpportunityStatusMutation.mutate({
                                opportunityId: opportunity.id,
                                status: value as OpportunityStatus,
                              })
                            }
                            disabled={updateOpportunityStatusMutation.isPending}
                          >
                            <SelectTrigger
                              className="h-7 w-[132px] text-xs"
                              aria-label={`Update status for ${opportunity.name}`}
                            >
                              <SelectValue placeholder="Status" />
                            </SelectTrigger>
                            <SelectContent>
                              {OPPORTUNITY_STATUSES.map((status) => (
                                <SelectItem key={status} value={status}>
                                  {status}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                    );
                  })
                )}
              </section>

              <Separator />

              <section
                aria-labelledby="inbox-context-agent"
                className="space-y-2"
              >
                <h3
                  id="inbox-context-agent"
                  className="px-2 text-sm font-medium text-muted-foreground"
                >
                  Active agent
                </h3>
                {conversation ? (
                  <div className="space-y-1.5 px-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex min-w-0 items-center gap-1.5 text-sm">
                        <Bot
                          aria-hidden
                          className="h-4 w-4 shrink-0 text-muted-foreground"
                        />
                        <span className="truncate">{assignedAgentName}</span>
                      </span>
                      <Badge
                        variant={conversation.ai_enabled ? "default" : "secondary"}
                        className="shrink-0 text-[10px]"
                      >
                        {conversation.ai_enabled ? "AI on" : "AI off"}
                      </Badge>
                    </div>
                    <Select
                      value={assignedAgentId ?? "none"}
                      onValueChange={handleAssignAgent}
                      disabled={
                        assignContactAgentMutation.isPending ||
                        assignConversationAgentMutation.isPending ||
                        isAgentsPending
                      }
                    >
                      <SelectTrigger
                        className="w-full"
                        aria-label="Assign agent to this conversation"
                      >
                        <SelectValue
                          placeholder={
                            isAgentsPending ? "Loading agents…" : "Assign agent"
                          }
                        />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">No agent</SelectItem>
                        {agents.map((agent) => (
                          <SelectItem key={agent.id} value={agent.id}>
                            <Bot aria-hidden className="h-4 w-4" />
                            {agent.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      Assigning an agent turns AI on; clearing it turns AI off.
                    </p>
                  </div>
                ) : (
                  <p className="px-2 text-sm text-muted-foreground">
                    No conversation yet.
                  </p>
                )}
              </section>
            </>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
