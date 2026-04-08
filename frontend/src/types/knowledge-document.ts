export interface KnowledgeDocument {
  id: string;
  workspace_id: string;
  agent_id: string;
  title: string;
  doc_type: string;
  content: string;
  token_count: number;
  priority: number;
  is_active: boolean;
  metadata_: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeDocumentListResponse {
  items: KnowledgeDocument[];
  total: number;
  total_tokens: number;
  token_budget: number;
}

export interface KnowledgeDocumentCreate {
  title: string;
  content: string;
  doc_type?: string;
  priority?: number;
  is_active?: boolean;
}

export interface KnowledgeDocumentUpdate {
  title?: string;
  content?: string;
  doc_type?: string;
  priority?: number;
  is_active?: boolean;
}
