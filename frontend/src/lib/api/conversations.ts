import api from "@/lib/api";
import { createApiClient } from "@/lib/api/create-api-client";
import type {
  Conversation,
  FollowupGenerateResponse,
  FollowupSendResponse,
  FollowupSettings,
  Message,
} from "@/types";

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

  getMessages: async (workspaceId: string, conversationId: string): Promise<Message[]> => {
    const response = await api.get<Message[]>(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/messages`
    );
    return response.data;
  },

  sendMessage: async (
    workspaceId: string,
    conversationId: string,
    body: string
  ): Promise<Message> => {
    const response = await api.post<Message>(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/messages`,
      { body }
    );
    return response.data;
  },

  toggleAI: async (
    workspaceId: string,
    conversationId: string,
    enabled: boolean
  ): Promise<{ ai_enabled: boolean }> => {
    const response = await api.post<{ ai_enabled: boolean }>(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/ai/toggle`,
      { enabled }
    );
    return response.data;
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
    const response = await api.post<Message>(
      `/api/v1/workspaces/${workspaceId}/contacts/${contactId}/messages`,
      { body, from_number: fromNumber }
    );
    return response.data;
  },

  assignAgent: async (
    workspaceId: string,
    conversationId: string,
    agentId: string | null
  ): Promise<{ assigned_agent_id: string | null }> => {
    const response = await api.post<{ assigned_agent_id: string | null }>(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/assign`,
      { agent_id: agentId }
    );
    return response.data;
  },

  clearHistory: async (
    workspaceId: string,
    conversationId: string
  ): Promise<void> => {
    await api.delete(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/messages`
    );
  },

  // Follow-up methods
  getFollowupSettings: async (
    workspaceId: string,
    conversationId: string
  ): Promise<FollowupSettings> => {
    const response = await api.get<FollowupSettings>(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/followup/status`
    );
    return response.data;
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
    const response = await api.patch<FollowupSettings>(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/followup/settings`,
      settings
    );
    return response.data;
  },

  generateFollowup: async (
    workspaceId: string,
    conversationId: string,
    customInstructions?: string
  ): Promise<FollowupGenerateResponse> => {
    const response = await api.post<FollowupGenerateResponse>(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/followup/generate`,
      { custom_instructions: customInstructions }
    );
    return response.data;
  },

  sendFollowup: async (
    workspaceId: string,
    conversationId: string,
    message?: string,
    customInstructions?: string
  ): Promise<FollowupSendResponse> => {
    const response = await api.post<FollowupSendResponse>(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/followup/send`,
      { message, custom_instructions: customInstructions }
    );
    return response.data;
  },

  resetFollowupCounter: async (
    workspaceId: string,
    conversationId: string
  ): Promise<{ count_sent: number }> => {
    const response = await api.post<{ count_sent: number }>(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/followup/reset`
    );
    return response.data;
  },
};
