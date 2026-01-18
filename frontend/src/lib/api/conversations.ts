import api from "@/lib/api";
import type {
  Conversation,
  FollowupGenerateResponse,
  FollowupSendResponse,
  FollowupSettings,
  Message,
  TimelineItem,
} from "@/types";

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
