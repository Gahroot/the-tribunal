// Message Test Types (A/B Testing)

export type MessageTestStatus = "draft" | "running" | "paused" | "completed";
export type TestContactStatus =
  | "pending"
  | "sent"
  | "delivered"
  | "replied"
  | "qualified"
  | "opted_out"
  | "failed";

export interface TestVariant {
  id: string;
  message_test_id: string;
  name: string;
  message_template: string;
  is_control: boolean;
  sort_order: number;
  contacts_assigned: number;
  messages_sent: number;
  replies_received: number;
  contacts_qualified: number;
  response_rate: number;
  qualification_rate: number;
  created_at: string;
  updated_at: string;
}

export interface TestContact {
  id: string;
  message_test_id: string;
  contact_id: number;
  variant_id?: string;
  conversation_id?: string;
  status: TestContactStatus;
  is_qualified: boolean;
  opted_out: boolean;
  first_sent_at?: string;
  last_reply_at?: string;
  variant_assigned_at?: string;
  created_at: string;
}

export interface MessageTest {
  id: string;
  workspace_id: string;
  agent_id?: string;
  name: string;
  description?: string;
  status: MessageTestStatus;
  from_phone_number: string;
  use_number_pool: boolean;
  ai_enabled: boolean;
  qualification_criteria?: string;
  sending_hours_start?: string;
  sending_hours_end?: string;
  sending_days?: number[];
  timezone: string;
  messages_per_minute: number;
  total_contacts: number;
  total_variants: number;
  messages_sent: number;
  replies_received: number;
  contacts_qualified: number;
  winning_variant_id?: string;
  converted_to_campaign_id?: string;
  started_at?: string;
  completed_at?: string;
  created_at: string;
  updated_at: string;
  variants?: TestVariant[];
}

export interface VariantAnalytics {
  variant_id: string;
  variant_name: string;
  is_control: boolean;
  contacts_assigned: number;
  messages_sent: number;
  replies_received: number;
  contacts_qualified: number;
  response_rate: number;
  qualification_rate: number;
}

export interface MessageTestAnalytics {
  test_id: string;
  test_name: string;
  status: MessageTestStatus;
  total_contacts: number;
  total_variants: number;
  messages_sent: number;
  replies_received: number;
  contacts_qualified: number;
  overall_response_rate: number;
  overall_qualification_rate: number;
  variants: VariantAnalytics[];
  winning_variant_id?: string;
  statistical_significance: boolean;
}

// Message Template Types (for saved experiment variations)
export interface MessageTemplate {
  id: string;
  workspace_id: string;
  name: string;
  message_template: string;
  created_at: string;
  updated_at: string;
}
