// Workspace types

export interface Workspace {
  id: string;
  user_id: number;
  name: string;
  description?: string;
  is_default: boolean;
  settings?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}
