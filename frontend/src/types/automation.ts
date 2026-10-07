// Automation types

// Generic/legacy trigger kinds plus the concrete event/polling triggers the
// backend automation worker evaluates.
export type AutomationTriggerType =
  | "schedule"
  | "event"
  | "condition"
  // Polling triggers (contact-centric)
  | "appointment_booked"
  | "booking_created"
  | "no_show"
  | "contact_tagged"
  | "never_booked"
  // Event triggers (emitted by services)
  | "review_received"
  | "review_request_response"
  | "opportunity_created"
  | "deal_stage_changed"
  | "missed_call"
  | "roleplay_completed"
  | "knowledge_document_uploaded";

// Action types the backend automation worker can execute, plus UI-only kinds
// retained for backward compatibility with existing automations.
export type AutomationActionType =
  | "send_sms"
  | "send_email"
  | "make_call"
  | "enroll_campaign"
  | "apply_tag"
  | "add_tag"
  | "wait"
  | "delay"
  | "update_status"
  | "assign_agent";

export interface AutomationAction {
  type: AutomationActionType;
  config: Record<string, unknown>;
}

/** One reason an automation cannot be activated yet (from the backend). */
export interface AutomationConfigIssue {
  code: string;
  /** Dotted path, e.g. `actions[0].config.message` or `trigger_config.tag`. */
  field: string;
  message: string;
}

/**
 * Stored outcome of the most recent run: `pending` while running,
 * `completed` when every action succeeded, `failed` with an actionable error.
 */
export interface AutomationExecutionSummary {
  id: string;
  status: "pending" | "completed" | "failed" | (string & {});
  error: string | null;
  contact_id: number | null;
  created_at: string;
  executed_at: string | null;
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
  /** `ready` when the engine can execute every part of the automation. */
  readiness: "ready" | "incomplete";
  config_issues: AutomationConfigIssue[];
  last_execution: AutomationExecutionSummary | null;
}
