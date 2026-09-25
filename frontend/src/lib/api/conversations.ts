import { apiGet, apiPost, apiPatch, apiDelete } from "@/lib/api";
import type { components } from "@/lib/api/_generated";
import { createApiClient } from "@/lib/api/create-api-client";
import type {
  Conversation,
  FollowupGenerateResponse,
  FollowupSendResponse,
  FollowupSettings,
  Message,
} from "@/types";


export type InboxView = keyof components["schemas"]["InboxCounts"];
export type InboxConversation = components["schemas"]["InboxConversationResponse"];
export type InboxResponse = components["schemas"]["PaginatedInbox"];
export type InboxContact = components["schemas"]["InboxContactSummary"];
export type InboxMessage = components["schemas"]["InboxMessageResponse"];
export interface InboxParams {
  view: InboxView;
  q: string;
  page: number;
  page_size: number;
}

export interface ConversationsListParams {
  page?: number;
  page_size?: number;
  status?: "active" | "archived" | "blocked";
  channel?: string;
  unread_only?: boolean;
  [key: string]: unknown;
}

export interface ConversationsListResponse {
  items: Conversation[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface SendMessageRequest {
  contact_id: number;
  body: string;
  channel: "sms" | "email";
  from_number?: string;
  to_number?: string;
}

// Create base API client with standard CRUD methods (list, get only - no create/update/delete)
const baseConversationsApi = createApiClient<Conversation, never, never>({
  resourcePath: "conversations",
  includeCreate: false,
  includeUpdate: false,
  includeDelete: false,
});

// Type assertion to ensure get is non-optional since we enabled it
const baseConversationsApiWithGet = baseConversationsApi as {
  list: typeof baseConversationsApi.list;
  get: NonNullable<typeof baseConversationsApi.get>;
};

export const conversationsApi = {
  ...baseConversationsApiWithGet,

  inbox: (workspaceId: string, params: InboxParams, signal?: AbortSignal) =>
    params.q
      ? apiPost<InboxResponse>(`/api/v1/workspaces/${workspaceId}/conversations/inbox/search`, params, { signal })
      : apiGet<InboxResponse>(`/api/v1/workspaces/${workspaceId}/conversations/inbox`, { params, signal }),

  inboxDetail: (workspaceId: string, conversationId: string, signal?: AbortSignal) =>
    apiGet<InboxConversation>(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/inbox-detail`, { signal },
    ),

  markRead: (workspaceId: string, conversation: InboxConversation) =>
    apiPost<components["schemas"]["MarkConversationReadResponse"]>(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversation.id}/read`,
      { last_message_at: conversation.last_message_at, unread_count: conversation.unread_count },
    ),

  getMessages: async (workspaceId: string, conversationId: string, signal?: AbortSignal): Promise<InboxMessage[]> => {
    return apiGet<InboxMessage[]>(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/messages`, { signal },
    );
  },

  sendMessage: async (
    workspaceId: string,
    conversationId: string,
    body: string
  ): Promise<Message> => {
    return apiPost<Message>(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/messages`,
      { body }
    );
  },

  toggleAI: async (
    workspaceId: string,
    conversationId: string,
    enabled: boolean
  ): Promise<{ ai_enabled: boolean }> => {
    return apiPost<{ ai_enabled: boolean }>(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/ai/toggle`,
      { enabled }
    );
  },

  /**
   * Send a message to a contact (creates/gets conversation automatically)
   * This is the recommended way to send messages from the conversation feed.
   */
  sendMessageToContact: async (
    workspaceId: string,
    contactId: number,
    body: string,
    fromNumber?: string
  ): Promise<Message> => {
    return apiPost<Message>(
      `/api/v1/workspaces/${workspaceId}/contacts/${contactId}/messages`,
      { body, from_number: fromNumber }
    );
  },

  assignAgent: async (
    workspaceId: string,
    conversationId: string,
    agentId: string | null
  ): Promise<{ assigned_agent_id: string | null }> => {
    return apiPost<{ assigned_agent_id: string | null }>(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/assign`,
      { agent_id: agentId }
    );
  },

  clearHistory: async (
    workspaceId: string,
    conversationId: string
  ): Promise<void> => {
    await apiDelete(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/messages`
    );
  },

  // Follow-up methods
  getFollowupSettings: async (
    workspaceId: string,
    conversationId: string
  ): Promise<FollowupSettings> => {
    return apiGet<FollowupSettings>(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/followup/status`
    );
  },

  updateFollowupSettings: async (
    workspaceId: string,
    conversationId: string,
    settings: Partial<{
      enabled: boolean;
      delay_hours: number;
      max_count: number;
    }>
  ): Promise<FollowupSettings> => {
    return apiPatch<FollowupSettings>(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/followup/settings`,
      settings
    );
  },

  generateFollowup: async (
    workspaceId: string,
    conversationId: string,
    customInstructions?: string,
    signal?: AbortSignal
  ): Promise<FollowupGenerateResponse> => {
    return apiPost<FollowupGenerateResponse>(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/followup/generate`,
      { custom_instructions: customInstructions },
      { signal }
    );
  },

  sendFollowup: async (
    workspaceId: string,
    conversationId: string,
    message?: string,
    customInstructions?: string
  ): Promise<FollowupSendResponse> => {
    return apiPost<FollowupSendResponse>(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/followup/send`,
      { message, custom_instructions: customInstructions }
    );
  },

  resetFollowupCounter: async (
    workspaceId: string,
    conversationId: string
  ): Promise<{ count_sent: number }> => {
    return apiPost<{ count_sent: number }>(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/followup/reset`
    );
  },
};
