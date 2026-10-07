// Static presentation config for automation triggers and actions: labels,
// icons, dropdown groupings, and animation variants shared across the
// Automations page presentational components.
import {
  ArrowRight,
  CalendarCheck,
  CalendarX,
  Clock,
  FileText,
  GraduationCap,
  Mail,
  Megaphone,
  MessageSquare,
  Phone,
  PhoneMissed,
  Settings2,
  Star,
  Tag,
  Timer,
  TrendingUp,
  UserCheck,
  UserPlus,
  Zap,
  type LucideIcon,
} from "lucide-react";

import type { AutomationActionType, AutomationTriggerType } from "@/types";

import type { AutomationDisplayState } from "./automation-logic";

export interface TriggerConfig {
  label: string;
  icon: LucideIcon;
  color: string;
  description: string;
}

export interface ActionConfig {
  label: string;
  icon: LucideIcon;
}

export const triggerTypeConfig: Record<AutomationTriggerType, TriggerConfig> = {
  event: { label: "Event", icon: Zap, color: "text-warning", description: "When an event occurs" },
  schedule: { label: "Schedule", icon: Clock, color: "text-info", description: "Runs on a schedule" },
  condition: { label: "Condition", icon: Settings2, color: "text-primary", description: "When conditions are met" },
  appointment_booked: { label: "Appointment Booked", icon: CalendarCheck, color: "text-success", description: "When a contact books an appointment" },
  booking_created: { label: "Booking Created", icon: CalendarCheck, color: "text-success", description: "When a booking is created" },
  no_show: { label: "No-show", icon: CalendarX, color: "text-destructive", description: "When a contact misses an appointment" },
  contact_tagged: { label: "Contact Tagged", icon: Tag, color: "text-primary", description: "When a contact gets a specific tag" },
  never_booked: { label: "Never Booked", icon: UserPlus, color: "text-warning", description: "When a contact never booked after engaging" },
  review_received: { label: "Review Received", icon: Star, color: "text-warning", description: "When a new review or rating comes in" },
  review_request_response: { label: "Review Request Response", icon: Star, color: "text-warning", description: "When a contact responds to a review request" },
  opportunity_created: { label: "Opportunity Created", icon: TrendingUp, color: "text-success", description: "When a new deal is created" },
  deal_stage_changed: { label: "Deal Stage Changed", icon: TrendingUp, color: "text-info", description: "When a deal moves to a new stage" },
  missed_call: { label: "Missed Call", icon: PhoneMissed, color: "text-destructive", description: "When an inbound call goes unanswered" },
  roleplay_completed: { label: "Roleplay Completed", icon: GraduationCap, color: "text-primary", description: "When a practice-arena rehearsal finishes" },
  knowledge_document_uploaded: { label: "Knowledge Doc Uploaded", icon: FileText, color: "text-info", description: "When a knowledge document is added" },
};

export const actionTypeConfig: Record<AutomationActionType, ActionConfig> = {
  send_sms: { label: "Send SMS", icon: MessageSquare },
  send_email: { label: "Send Email", icon: Mail },
  make_call: { label: "Make Call", icon: Phone },
  enroll_campaign: { label: "Enroll in Campaign", icon: Megaphone },
  apply_tag: { label: "Apply Tag", icon: Tag },
  add_tag: { label: "Add Tag", icon: Tag },
  wait: { label: "Wait", icon: Timer },
  delay: { label: "Delay", icon: Timer },
  update_status: { label: "Update Status", icon: Settings2 },
  assign_agent: { label: "Assign Agent", icon: UserCheck },
};

// Triggers offered in the builder dropdown, grouped for readability. The
// generic event/schedule/condition kinds are not run by the engine, so they
// are only shown when editing a legacy automation that still uses one.
export const TRIGGER_OPTIONS: { group: string; values: AutomationTriggerType[] }[] = [
  { group: "Appointments", values: ["appointment_booked", "booking_created", "no_show", "never_booked"] },
  { group: "Contacts & Pipeline", values: ["contact_tagged", "opportunity_created", "deal_stage_changed"] },
  { group: "Engagement", values: ["review_received", "review_request_response", "missed_call", "roleplay_completed", "knowledge_document_uploaded"] },
];

// Actions offered in the builder dropdown (all executed by the engine).
export const ACTION_OPTIONS: AutomationActionType[] = [
  "send_sms",
  "send_email",
  "make_call",
  "enroll_campaign",
  "apply_tag",
];

// Inline guidance shown under the trigger select.
export const TRIGGER_GUIDANCE: Partial<Record<AutomationTriggerType, string>> = {
  appointment_booked: "Runs once for each contact whose appointment is scheduled.",
  booking_created: "Runs once for each contact with a new booking.",
  no_show: "Runs once for each contact marked as a no-show.",
  contact_tagged: "Runs once for each contact that has the tag below.",
  never_booked:
    "Runs for contacts created at least this many days ago who never booked.",
  missed_call: "Runs for the caller when an inbound call goes unanswered.",
  roleplay_completed:
    "Has no contact, so contact actions (SMS, email, calls, tags) cannot run.",
  knowledge_document_uploaded:
    "Has no contact, so contact actions (SMS, email, calls, tags) cannot run.",
};

// Inline guidance shown under each action step.
export const ACTION_GUIDANCE: Partial<Record<AutomationActionType, string>> = {
  send_sms:
    "Sent from an active SMS number in this workspace. Opted-out contacts are skipped and the run is marked failed.",
  send_email: "Requires the contact to have an email address.",
  make_call:
    "Calls from an active voice number. Pick an agent to talk, or leave it on default.",
  enroll_campaign:
    "The campaign must be running or scheduled when the automation fires.",
  apply_tag: "Adds the tag to the contact.",
  add_tag: "Adds the tag to the contact.",
};

export const TEMPLATE_TOKENS_HINT =
  "Use {first_name}, {last_name}, {full_name}, {company_name} or {email} to personalize.";

// Card status presentation (dot + label, see `StatusBadge`).
export const displayStateConfig: Record<
  AutomationDisplayState,
  { label: string; dotClass: string }
> = {
  incomplete: { label: "Needs setup", dotClass: "bg-warning" },
  paused: { label: "Paused", dotClass: "bg-muted-foreground" },
  ready: { label: "Ready", dotClass: "bg-info" },
  running: { label: "Running", dotClass: "bg-info" },
  succeeded: { label: "Last run succeeded", dotClass: "bg-success" },
  failed: { label: "Last run failed", dotClass: "bg-destructive" },
};

/** Resolve a trigger's display config, falling back to a generic descriptor. */
export function resolveTriggerConfig(type: AutomationTriggerType): TriggerConfig {
  return (
    triggerTypeConfig[type] ?? {
      label: type,
      icon: Zap,
      color: "text-muted-foreground",
      description: "Custom trigger",
    }
  );
}

/** Resolve an action's display config, falling back to a generic descriptor. */
export function resolveActionConfig(type: AutomationActionType): ActionConfig {
  return actionTypeConfig[type] ?? { label: type, icon: Settings2 };
}

export const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.1 },
  },
};

export const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 },
};

export { ArrowRight };
