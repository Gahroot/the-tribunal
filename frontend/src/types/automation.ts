// Automation types

export type AutomationTriggerType = "schedule" | "event" | "condition";
export type AutomationActionType = "send_sms" | "send_email" | "make_call" | "update_status" | "add_tag" | "assign_agent";

export interface AutomationAction {
  type: AutomationActionType;
  config: Record<string, unknown>;
}

export interface Automation {
  id: string;
  name: string;
  description?: string;
  trigger_type: AutomationTriggerType;
  trigger_config?: Record<string, unknown>;
  actions: AutomationAction[];
  is_active: boolean;
  last_triggered_at?: string;
  created_at: string;
  updated_at: string;
}
