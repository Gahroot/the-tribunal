import api from "@/lib/api";
import type { Conversation, Message, TimelineItem } from "@/types";

export interface ConversationsListParams {
  page?: number;
  page_size?: number;
  status?: "active" | "archived" | "blocked";
  channel?: string;
  unread_only?: boolean;
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

export const conversationsApi = {
  list: async (
    workspaceId: string,
    params: ConversationsListParams = {}
  ): Promise<ConversationsListResponse> => {
    const response = await api.get<ConversationsListResponse>(
      `/api/v1/workspaces/${workspaceId}/conversations`,
      { params }
    );
    return response.data;
  },

  get: async (workspaceId: string, id: string): Promise<Conversation> => {
    const response = await api.get<Conversation>(
      `/api/v1/workspaces/${workspaceId}/conversations/${id}`
    );
    return response.data;
  },

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

  markAsRead: async (workspaceId: string, conversationId: string): Promise<void> => {
    await api.post(
      `/api/v1/workspaces/${workspaceId}/conversations/${conversationId}/read`
    );
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

  // Get unified timeline for a contact (combines SMS, calls, appointments)
  getContactTimeline: async (contactId: number): Promise<TimelineItem[]> => {
    const response = await api.get<TimelineItem[]>(
      `/api/v1/crm/contacts/${contactId}/timeline`
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
};
