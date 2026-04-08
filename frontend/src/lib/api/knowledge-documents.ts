import { apiGet, apiPost, apiPatch, apiDelete } from "@/lib/api";
import type {
  KnowledgeDocument,
  KnowledgeDocumentListResponse,
  KnowledgeDocumentCreate,
  KnowledgeDocumentUpdate,
} from "@/types/knowledge-document";

export const knowledgeDocumentsApi = {
  list: async (
    workspaceId: string,
    agentId: string
  ): Promise<KnowledgeDocumentListResponse> => {
    return apiGet<KnowledgeDocumentListResponse>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/knowledge`
    );
  },

  create: async (
    workspaceId: string,
    agentId: string,
    data: KnowledgeDocumentCreate
  ): Promise<KnowledgeDocument> => {
    return apiPost<KnowledgeDocument>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/knowledge`,
      data
    );
  },

  get: async (
    workspaceId: string,
    agentId: string,
    documentId: string
  ): Promise<KnowledgeDocument> => {
    return apiGet<KnowledgeDocument>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/knowledge/${documentId}`
    );
  },

  update: async (
    workspaceId: string,
    agentId: string,
    documentId: string,
    data: KnowledgeDocumentUpdate
  ): Promise<KnowledgeDocument> => {
    return apiPatch<KnowledgeDocument>(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/knowledge/${documentId}`,
      data
    );
  },

  remove: async (
    workspaceId: string,
    agentId: string,
    documentId: string
  ): Promise<void> => {
    return apiDelete(
      `/api/v1/workspaces/${workspaceId}/agents/${agentId}/knowledge/${documentId}`
    );
  },
};
