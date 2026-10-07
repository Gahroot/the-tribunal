import { describe, expect, it } from "vitest";

import type { Automation, AutomationActionType } from "@/types";

import {
  DEFAULT_INACTIVITY_DAYS,
  DEFAULT_SMS_MESSAGE,
  EMPTY_AUTOMATION_FORM,
  type AutomationFormState,
  automationToForm,
  buildCreatePayload,
  buildDuplicatePayload,
  buildUpdatePayload,
  changeActionType,
  changeTrigger,
  countActive,
  defaultActionConfig,
  filterAutomations,
  getAutomationDisplayState,
  getFormIssues,
  issuesFor,
  removeAction,
  setActionField,
} from "./automation-logic";

function makeAutomation(overrides: Partial<Automation> = {}): Automation {
  return {
    id: "auto-1",
    name: "New Lead Welcome",
    description: "Greets every new lead",
    trigger_type: "appointment_booked",
    trigger_config: { foo: "bar" },
    actions: [{ type: "send_email", config: { template: "welcome" } }],
    is_active: true,
    last_triggered_at: "2026-06-14T12:00:00.000Z",
    created_at: "2026-06-01T00:00:00.000Z",
    updated_at: "2026-06-10T00:00:00.000Z",
    readiness: "ready",
    config_issues: [],
    last_execution: null,
    ...overrides,
  };
}

describe("default Send SMS automation (first use)", () => {
  it("starts on a runnable trigger with a real SMS template", () => {
    expect(EMPTY_AUTOMATION_FORM.triggerType).toBe("no_show");
    expect(EMPTY_AUTOMATION_FORM.actions).toEqual([
      { type: "send_sms", config: { message: DEFAULT_SMS_MESSAGE } },
    ]);
    expect(EMPTY_AUTOMATION_FORM.isActive).toBe(true);
    expect(getFormIssues(EMPTY_AUTOMATION_FORM)).toEqual([]);
  });

  it("sends the configured message, not an empty config", () => {
    const payload = buildCreatePayload({ ...EMPTY_AUTOMATION_FORM, name: " Follow up " });
    expect(payload).toEqual({
      name: "Follow up",
      description: undefined,
      trigger_type: "no_show",
      trigger_config: {},
      actions: [{ type: "send_sms", config: { message: DEFAULT_SMS_MESSAGE } }],
      is_active: true,
    });
  });

  it("flags a cleared message on the message field", () => {
    const form = {
      ...EMPTY_AUTOMATION_FORM,
      ...setActionField(EMPTY_AUTOMATION_FORM, 0, "message", "   "),
    };
    const issues = getFormIssues(form);
    expect(issuesFor(issues, "actions[0].config.message")).toEqual([
      "Step 1: write the text message to send.",
    ]);
  });

  it("can be saved as an incomplete draft", () => {
    const form: AutomationFormState = {
      ...EMPTY_AUTOMATION_FORM,
      actions: [{ type: "send_sms", config: {} }],
      isActive: false,
    };
    expect(buildCreatePayload(form).is_active).toBe(false);
  });
});

describe("getFormIssues: required settings per supported type", () => {
  const withAction = (type: AutomationActionType, config: Record<string, unknown> = {}) =>
    ({ ...EMPTY_AUTOMATION_FORM, actions: [{ type, config }] }) as AutomationFormState;

  it("requires an email subject and body", () => {
    const fields = getFormIssues(withAction("send_email")).map((i) => i.field);
    expect(fields).toEqual(["actions[0].config.subject", "actions[0].config.message"]);
    expect(getFormIssues(withAction("send_email", defaultActionConfig("send_email")))).toEqual([]);
  });

  it("requires a campaign for enroll_campaign", () => {
    expect(getFormIssues(withAction("enroll_campaign", { campaign_id: "" }))[0].field).toBe(
      "actions[0].config.campaign_id",
    );
    expect(
      getFormIssues(
        withAction("enroll_campaign", { campaign_id: "3f2b8a1e-1111-4c2d-9a7b-123456789abc" }),
      ),
    ).toEqual([]);
  });

  it("requires a tag for apply_tag and allows default call handling", () => {
    expect(getFormIssues(withAction("apply_tag", { tag: "" }))[0].field).toBe(
      "actions[0].config.tag",
    );
    expect(getFormIssues(withAction("make_call"))).toEqual([]);
  });

  it("rejects steps and triggers the engine does not run", () => {
    expect(getFormIssues(withAction("wait", { hours: 1 }))[0].field).toBe("actions[0].type");
    expect(
      getFormIssues({ ...EMPTY_AUTOMATION_FORM, triggerType: "event" })[0].field,
    ).toBe("trigger_type");
  });

  it("requires a trigger tag for contact_tagged and validates inactivity days", () => {
    const tagged = { ...EMPTY_AUTOMATION_FORM, ...changeTrigger(EMPTY_AUTOMATION_FORM, "contact_tagged") };
    expect(getFormIssues(tagged).map((i) => i.field)).toEqual(["trigger_config.tag"]);

    const neverBooked = {
      ...EMPTY_AUTOMATION_FORM,
      ...changeTrigger(EMPTY_AUTOMATION_FORM, "never_booked"),
    };
    expect(neverBooked.triggerConfig).toEqual({ inactivity_days: DEFAULT_INACTIVITY_DAYS });
    expect(getFormIssues(neverBooked)).toEqual([]);
    expect(
      getFormIssues({ ...neverBooked, triggerConfig: { inactivity_days: 0 } })[0].field,
    ).toBe("trigger_config.inactivity_days");
  });

  it("checks every step, not only the first", () => {
    const form: AutomationFormState = {
      ...EMPTY_AUTOMATION_FORM,
      actions: [
        { type: "send_sms", config: { message: "Hi" } },
        { type: "apply_tag", config: {} },
      ],
    };
    expect(getFormIssues(form).map((i) => i.field)).toEqual(["actions[1].config.tag"]);
  });
});

describe("edit round-trip", () => {
  const stored = makeAutomation({
    trigger_type: "contact_tagged",
    trigger_config: { tag: "hot-lead" },
    actions: [
      { type: "send_sms", config: { message: "Hi {first_name}", extra: 1 } },
      { type: "apply_tag", config: { tag: "texted" } },
    ],
    is_active: false,
  });

  it("seeds every step, trigger config and active state", () => {
    expect(automationToForm(stored)).toEqual<AutomationFormState>({
      name: "New Lead Welcome",
      description: "Greets every new lead",
      triggerType: "contact_tagged",
      triggerConfig: { tag: "hot-lead" },
      actions: stored.actions,
      isActive: false,
    });
  });

  it("saving unchanged returns the stored configuration", () => {
    const payload = buildUpdatePayload(automationToForm(stored));
    expect(payload).toEqual({
      name: "New Lead Welcome",
      description: "Greets every new lead",
      trigger_type: "contact_tagged",
      trigger_config: { tag: "hot-lead" },
      actions: stored.actions,
      is_active: false,
    });
  });

  it("editing one field keeps other keys and extra steps", () => {
    const form = automationToForm(stored);
    const edited = { ...form, ...setActionField(form, 0, "message", "Updated") };
    expect(buildUpdatePayload(edited).actions).toEqual([
      { type: "send_sms", config: { message: "Updated", extra: 1 } },
      { type: "apply_tag", config: { tag: "texted" } },
    ]);
    // Seeding copies config, so editing never mutates the cached automation.
    expect(stored.actions[0].config.message).toBe("Hi {first_name}");
  });

  it("re-selecting the same type keeps config; a new type gets defaults", () => {
    const form = automationToForm(stored);
    expect(changeActionType(form, 0, "send_sms").actions?.[0]).toEqual(form.actions[0]);
    expect(changeTrigger(form, "contact_tagged")).toEqual({});
    expect(changeActionType(form, 1, "send_email").actions?.[1]).toEqual({
      type: "send_email",
      config: defaultActionConfig("send_email"),
    });
  });

  it("removes a step but never the last one", () => {
    const form = automationToForm(stored);
    expect(removeAction(form, 1).actions).toHaveLength(1);
    expect(removeAction({ ...form, actions: [form.actions[0]] }, 0)).toEqual({});
  });
});

describe("getAutomationDisplayState", () => {
  const exec = (status: string, error: string | null = null) => ({
    id: "e1",
    status,
    error,
    contact_id: 1,
    created_at: "2026-06-10T00:00:00.000Z",
    executed_at: null,
  });

  it("distinguishes setup state from run outcomes", () => {
    expect(getAutomationDisplayState(makeAutomation({ readiness: "incomplete" }))).toBe(
      "incomplete",
    );
    expect(getAutomationDisplayState(makeAutomation({ is_active: false }))).toBe("paused");
    expect(getAutomationDisplayState(makeAutomation())).toBe("ready");
    expect(
      getAutomationDisplayState(makeAutomation({ last_execution: exec("pending") })),
    ).toBe("running");
    expect(
      getAutomationDisplayState(makeAutomation({ last_execution: exec("completed") })),
    ).toBe("succeeded");
    expect(
      getAutomationDisplayState(makeAutomation({ last_execution: exec("failed", "x") })),
    ).toBe("failed");
  });
});

describe("buildDuplicatePayload", () => {
  it("clones the automation as a paused copy preserving config", () => {
    const original = makeAutomation();
    const payload = buildDuplicatePayload(original);
    expect(payload).toEqual({
      name: "New Lead Welcome (Copy)",
      description: "Greets every new lead",
      trigger_type: "appointment_booked",
      trigger_config: { foo: "bar" },
      actions: [{ type: "send_email", config: { template: "welcome" } }],
      is_active: false,
    });
  });
});

describe("filterAutomations", () => {
  const items = [
    makeAutomation({ id: "a", name: "Welcome SMS", description: "greet" }),
    makeAutomation({ id: "b", name: "No-show recovery", description: "win back" }),
    makeAutomation({ id: "c", name: "Quiet", description: undefined }),
  ];

  it("returns everything for an empty/whitespace query", () => {
    expect(filterAutomations(items, "")).toHaveLength(3);
    expect(filterAutomations(items, "   ")).toHaveLength(3);
  });

  it("matches against name case-insensitively", () => {
    const result = filterAutomations(items, "welcome");
    expect(result.map((a) => a.id)).toEqual(["a"]);
  });

  it("matches against description", () => {
    const result = filterAutomations(items, "win back");
    expect(result.map((a) => a.id)).toEqual(["b"]);
  });

  it("handles automations without a description", () => {
    const result = filterAutomations(items, "quiet");
    expect(result.map((a) => a.id)).toEqual(["c"]);
  });
});

describe("countActive", () => {
  it("counts only active automations", () => {
    const items = [
      makeAutomation({ id: "a", is_active: true }),
      makeAutomation({ id: "b", is_active: false }),
      makeAutomation({ id: "c", is_active: true }),
    ];
    expect(countActive(items)).toBe(2);
  });

  it("returns 0 for an empty list", () => {
    expect(countActive([])).toBe(0);
  });
});
