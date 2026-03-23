// Filter and Segment types

export interface FilterRule {
  field: string;
  operator: string;
  value: string | number | boolean | string[] | number[];
}

export interface FilterDefinition {
  logic: "and" | "or";
  rules: FilterRule[];
}

export interface Segment {
  id: string;
  workspace_id: string;
  name: string;
  description?: string;
  definition: FilterDefinition;
  is_dynamic: boolean;
  contact_count: number;
  last_computed_at?: string;
  created_at: string;
  updated_at: string;
}
