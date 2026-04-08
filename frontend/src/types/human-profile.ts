export interface HumanProfile {
  id: string;
  workspace_id: string;
  agent_id: string;
  display_name: string;
  role_title: string | null;
  phone_number: string | null;
  email: string | null;
  timezone: string;
  bio: string | null;
  communication_preferences: Record<string, unknown>;
  action_policies: Record<string, string>;
  default_policy: string;
  auto_approve_timeout_minutes: number;
  auto_reject_timeout_minutes: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface HumanProfileCreate {
  display_name: string;
  role_title?: string;
  phone_number?: string;
  email?: string;
  timezone?: string;
  bio?: string;
  communication_preferences?: Record<string, unknown>;
  action_policies?: Record<string, string>;
  default_policy?: string;
  auto_approve_timeout_minutes?: number;
  auto_reject_timeout_minutes?: number;
}

export type HumanProfileUpdate = Partial<HumanProfileCreate>;
