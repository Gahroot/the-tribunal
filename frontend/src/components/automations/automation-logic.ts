// Pure, framework-free logic for the Automations page. Kept free of React and
// JSX so the form/payload/derivation rules can be unit-tested in isolation.
//
// Readiness rules mirror backend `app/services/automations/validation.py`,
// which is the authority: the API refuses to activate an incomplete
// automation. The client copy only drives inline guidance before submit.
import type {
  CreateAutomationRequest,
  UpdateAutomationRequest,
} from "@/lib/api/automations";
import type {
  Automation,
  AutomationAction,
  AutomationActionType,
  AutomationTriggerType,
} from "@/types";

export interface AutomationFormState {
  name: string;
  description: string;
  triggerType: AutomationTriggerType;
  triggerConfig: Record<string, unknown>;
  /** Every step of the automation, preserved in order (including extras). */
  actions: AutomationAction[];
  /** Whether the automation should run after saving. */
  isActive: boolean;
}

/** Triggers the automation engine evaluates (legacy kinds are never run). */
export const RUNNABLE_TRIGGERS: readonly AutomationTriggerType[] = [
  "appointment_booked",
  "booking_created",
  "no_show",
  "contact_tagged",
  "never_booked",
  "review_received",
  "review_request_response",
  "opportunity_created",
  "deal_stage_changed",
  "missed_call",
  "roleplay_completed",
  "knowledge_document_uploaded",
];

/** Action types the automation engine executes. */
export const RUNNABLE_ACTIONS: readonly AutomationActionType[] = [
  "send_sms",
  "send_email",
  "make_call",
  "enroll_campaign",
  "apply_tag",
  "add_tag",
];

/** Event triggers without a contact: contact actions cannot run for them. */
export const CONTACTLESS_TRIGGERS: readonly AutomationTriggerType[] = [
  "roleplay_completed",
  "knowledge_document_uploaded",
];

export const DEFAULT_SMS_MESSAGE =
  "Hi {first_name}, sorry we missed you! Reply here and we'll find a new time that works.";

export const DEFAULT_INACTIVITY_DAYS = 7;

/** Sensible starting config when an operator picks an action type. */
export function defaultActionConfig(
  type: AutomationActionType,
): Record<string, unknown> {
  switch (type) {
    case "send_sms":
      return { message: DEFAULT_SMS_MESSAGE };
    case "send_email":
      return {
        subject: "Following up, {first_name}",
        message:
          "Hi {first_name},\n\nJust following up. Reply to this email and we'll help you with next steps.",
      };
    case "enroll_campaign":
      return { campaign_id: "" };
    case "apply_tag":
    case "add_tag":
      return { tag: "" };
    default:
      return {};
  }
}

/** Sensible starting config when an operator picks a trigger type. */
export function defaultTriggerConfig(
  type: AutomationTriggerType,
): Record<string, unknown> {
  switch (type) {
    case "contact_tagged":
      return { tag: "" };
    case "never_booked":
      return { inactivity_days: DEFAULT_INACTIVITY_DAYS };
    default:
      return {};
  }
}

export const EMPTY_AUTOMATION_FORM: AutomationFormState = {
  name: "",
  description: "",
  triggerType: "no_show",
  triggerConfig: {},
  actions: [{ type: "send_sms", config: defaultActionConfig("send_sms") }],
  isActive: true,
};

/** Seed the builder form from an existing automation for the edit flow. */
export function automationToForm(automation: Automation): AutomationFormState {
  return {
    name: automation.name,
    description: automation.description ?? "",
    triggerType: automation.trigger_type,
    triggerConfig: { ...(automation.trigger_config ?? {}) },
    actions: automation.actions.map((action) => ({
      type: action.type,
      config: { ...(action.config ?? {}) },
    })),
    isActive: automation.is_active,
  };
}

/** Switch the trigger, keeping its config when the type is unchanged. */
export function changeTrigger(
  form: AutomationFormState,
  triggerType: AutomationTriggerType,
): Partial<AutomationFormState> {
  if (triggerType === form.triggerType) return {};
  return { triggerType, triggerConfig: defaultTriggerConfig(triggerType) };
}

/** Patch one key of the trigger config. */
export function setTriggerField(
  form: AutomationFormState,
  key: string,
  value: unknown,
): Partial<AutomationFormState> {
  return { triggerConfig: { ...form.triggerConfig, [key]: value } };
}

/** Switch a step's action type, keeping its config when unchanged. */
export function changeActionType(
  form: AutomationFormState,
  index: number,
  type: AutomationActionType,
): Partial<AutomationFormState> {
  return {
    actions: form.actions.map((action, i) =>
      i === index && action.type !== type
        ? { type, config: defaultActionConfig(type) }
        : action,
    ),
  };
}

/** Patch one key of a step's config, leaving other keys and steps intact. */
export function setActionField(
  form: AutomationFormState,
  index: number,
  key: string,
  value: unknown,
): Partial<AutomationFormState> {
  return {
    actions: form.actions.map((action, i) =>
      i === index
        ? { ...action, config: { ...action.config, [key]: value } }
        : action,
    ),
  };
}

/** Remove a step (the last remaining step cannot be removed). */
export function removeAction(
  form: AutomationFormState,
  index: number,
): Partial<AutomationFormState> {
  if (form.actions.length <= 1) return {};
  return { actions: form.actions.filter((_, i) => i !== index) };
}

export interface FormIssue {
  /** Same dotted path the backend uses, e.g. `actions[0].config.message`. */
  field: string;
  message: string;
}

const text = (value: unknown): string =>
  typeof value === "string" ? value.trim() : "";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function triggerIssues(form: AutomationFormState): FormIssue[] {
  const trigger = form.triggerType;
  if (!RUNNABLE_TRIGGERS.includes(trigger)) {
    return [
      {
        field: "trigger_type",
        message:
          "This trigger is not run by the automation engine. Choose a specific trigger.",
      },
    ];
  }
  if (trigger === "contact_tagged" && !text(form.triggerConfig.tag)) {
    return [
      {
        field: "trigger_config.tag",
        message: "Enter the tag that should start this automation.",
      },
    ];
  }
  if (trigger === "never_booked" && "inactivity_days" in form.triggerConfig) {
    const days = Number(form.triggerConfig.inactivity_days);
    if (!Number.isInteger(days) || days < 1 || days > 365) {
      return [
        {
          field: "trigger_config.inactivity_days",
          message: "Inactivity days must be a whole number between 1 and 365.",
        },
      ];
    }
  }
  return [];
}

function actionIssues(
  action: AutomationAction,
  index: number,
  trigger: AutomationTriggerType,
): FormIssue[] {
  const prefix = `actions[${index}]`;
  const step = `Step ${index + 1}`;
  const config = action.config ?? {};
  if (!RUNNABLE_ACTIONS.includes(action.type)) {
    return [
      {
        field: `${prefix}.type`,
        message: `${step}: this step is not run by the automation engine. Replace or remove it.`,
      },
    ];
  }
  const issues: FormIssue[] = [];
  if (CONTACTLESS_TRIGGERS.includes(trigger)) {
    issues.push({
      field: `${prefix}.type`,
      message: `${step}: this trigger has no contact, so contact actions cannot run.`,
    });
  }
  const require = (ok: boolean, key: string, message: string) => {
    if (!ok) {
      issues.push({
        field: `${prefix}.config.${key}`,
        message: `${step}: ${message}`,
      });
    }
  };
  switch (action.type) {
    case "send_sms":
      require(!!text(config.message), "message", "write the text message to send.");
      break;
    case "send_email":
      require(!!text(config.subject), "subject", "enter an email subject.");
      require(
        !!(text(config.message) || text(config.body)),
        "message",
        "write the email body.",
      );
      break;
    case "enroll_campaign":
      require(
        UUID_RE.test(text(config.campaign_id)),
        "campaign_id",
        "choose the campaign to enroll contacts in.",
      );
      break;
    case "apply_tag":
    case "add_tag":
      require(!!text(config.tag), "tag", "enter the tag to apply.");
      break;
    default:
      break;
  }
  return issues;
}

/** Every reason the automation could not run if activated now. */
export function getFormIssues(form: AutomationFormState): FormIssue[] {
  const issues = triggerIssues(form);
  if (form.actions.length === 0) {
    issues.push({ field: "actions", message: "Add at least one action." });
  }
  form.actions.forEach((action, index) => {
    issues.push(...actionIssues(action, index, form.triggerType));
  });
  return issues;
}

/** Messages for one field path, for inline display beside that input. */
export function issuesFor(issues: FormIssue[], field: string): string[] {
  return issues.filter((i) => i.field === field).map((i) => i.message);
}

/** Build the request body for creating a brand-new automation. */
export function buildCreatePayload(
  form: AutomationFormState,
): CreateAutomationRequest {
  return {
    name: form.name.trim(),
    description: form.description || undefined,
    trigger_type: form.triggerType,
    trigger_config: form.triggerConfig,
    actions: form.actions,
    is_active: form.isActive,
  };
}

/**
 * Build the request body for updating an existing automation. Sends the full
 * edited trigger config and every step so nothing is dropped or emptied.
 */
export function buildUpdatePayload(
  form: AutomationFormState,
): UpdateAutomationRequest {
  return {
    name: form.name.trim(),
    // Sent as-is so clearing the description sticks.
    description: form.description,
    trigger_type: form.triggerType,
    trigger_config: form.triggerConfig,
    actions: form.actions,
    is_active: form.isActive,
  };
}

/** Build the request body that clones an automation as a paused copy. */
export function buildDuplicatePayload(
  automation: Automation,
): CreateAutomationRequest {
  return {
    name: `${automation.name} (Copy)`,
    description: automation.description,
    trigger_type: automation.trigger_type,
    trigger_config: automation.trigger_config,
    actions: automation.actions,
    is_active: false,
  };
}

export type AutomationDisplayState =
  | "incomplete"
  | "paused"
  | "ready"
  | "running"
  | "succeeded"
  | "failed";

/**
 * Derive one status for the card: setup state first (incomplete/paused),
 * then the latest run outcome (running/succeeded/failed), else ready.
 */
export function getAutomationDisplayState(
  automation: Automation,
): AutomationDisplayState {
  if (automation.readiness === "incomplete") return "incomplete";
  if (!automation.is_active) return "paused";
  switch (automation.last_execution?.status) {
    case "pending":
      return "running";
    case "completed":
      return "succeeded";
    case "failed":
      return "failed";
    default:
      return "ready";
  }
}

/** Filter automations by a free-text query over name and description. */
export function filterAutomations(
  automations: Automation[],
  query: string,
): Automation[] {
  const normalized = query.trim().toLowerCase();
  if (!normalized) return automations;
  return automations.filter(
    (automation) =>
      automation.name.toLowerCase().includes(normalized) ||
      (automation.description?.toLowerCase().includes(normalized) ?? false),
  );
}

/** Count active automations. */
export function countActive(automations: Automation[]): number {
  return automations.filter((automation) => automation.is_active).length;
}
