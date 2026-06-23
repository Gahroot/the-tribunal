// Pure, framework-free logic for the Automations page. Kept free of React and
// JSX so the form/payload/derivation rules can be unit-tested in isolation.
import type {
  CreateAutomationRequest,
  UpdateAutomationRequest,
} from "@/lib/api/automations";
import type {
  Automation,
  AutomationActionType,
  AutomationTriggerType,
} from "@/types";

export interface AutomationFormState {
  name: string;
  description: string;
  triggerType: AutomationTriggerType;
  actionType: AutomationActionType;
}

export const EMPTY_AUTOMATION_FORM: AutomationFormState = {
  name: "",
  description: "",
  triggerType: "event",
  actionType: "send_sms",
};

/** Seed the builder form from an existing automation for the edit flow. */
export function automationToForm(automation: Automation): AutomationFormState {
  return {
    name: automation.name,
    description: automation.description ?? "",
    triggerType: automation.trigger_type,
    actionType: automation.actions[0]?.type ?? "send_sms",
  };
}

/** Build the request body for creating a brand-new automation. */
export function buildCreatePayload(
  form: AutomationFormState,
): CreateAutomationRequest {
  return {
    name: form.name,
    description: form.description || undefined,
    trigger_type: form.triggerType,
    trigger_config: {},
    actions: [{ type: form.actionType, config: {} }],
    is_active: true,
  };
}

/** Build the request body for updating an existing automation. */
export function buildUpdatePayload(
  form: AutomationFormState,
): UpdateAutomationRequest {
  return {
    name: form.name,
    description: form.description || undefined,
    trigger_type: form.triggerType,
    actions: [{ type: form.actionType, config: {} }],
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
