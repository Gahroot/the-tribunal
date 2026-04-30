/** CRM Assistant API client. */

import api from "@/lib/api";

export interface AssistantChatResponse {
  response: string;
  actions_taken: { tool_name: string; success: boolean; summary: string }[];
}

export interface AssistantMessageResponse {
  id: string;
  role: string;
  content: string;
  tool_calls?: { id: string; function: { name: string; arguments: string } }[];
  tool_call_id?: string;
  created_at: string;
}

export interface AssistantConversationResponse {
  id: string;
  messages: AssistantMessageResponse[];
  created_at: string;
}

const basePath = (workspaceId: string) =>
  `/api/v1/workspaces/${workspaceId}/assistant`;

export const assistantApi = {
  chat: async (
    workspaceId: string,
    message: string,
  ): Promise<AssistantChatResponse> => {
    const { data } = await api.post<AssistantChatResponse>(
      `${basePath(workspaceId)}/chat`,
      { message },
    );
    return data;
  },

  getHistory: async (
    workspaceId: string,
  ): Promise<AssistantConversationResponse | null> => {
    const { data } = await api.get<AssistantConversationResponse | null>(
      `${basePath(workspaceId)}/history`,
    );
    return data;
  },
};
