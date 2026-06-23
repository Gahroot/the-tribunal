import { describe, expect, it } from "vitest";

import type { Automation } from "@/types";

import {
  EMPTY_AUTOMATION_FORM,
  type AutomationFormState,
  automationToForm,
  buildCreatePayload,
  buildDuplicatePayload,
  buildUpdatePayload,
  countActive,
  filterAutomations,
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
    ...overrides,
  };
}

describe("automationToForm", () => {
  it("seeds the form from an existing automation", () => {
    const form = automationToForm(makeAutomation());
    expect(form).toEqual<AutomationFormState>({
      name: "New Lead Welcome",
      description: "Greets every new lead",
      triggerType: "appointment_booked",
      actionType: "send_email",
    });
  });

  it("defaults missing description and action to safe values", () => {
    const form = automationToForm(
      makeAutomation({ description: undefined, actions: [] }),
    );
    expect(form.description).toBe("");
    expect(form.actionType).toBe("send_sms");
  });
});

describe("buildCreatePayload", () => {
  it("builds an active automation with a single action", () => {
    const payload = buildCreatePayload({
      name: "Welcome",
      description: "desc",
      triggerType: "missed_call",
      actionType: "make_call",
    });
    expect(payload).toEqual({
      name: "Welcome",
      description: "desc",
      trigger_type: "missed_call",
      trigger_config: {},
      actions: [{ type: "make_call", config: {} }],
      is_active: true,
    });
  });

  it("omits an empty description", () => {
    const payload = buildCreatePayload({ ...EMPTY_AUTOMATION_FORM, name: "X" });
    expect(payload.description).toBeUndefined();
  });
});

describe("buildUpdatePayload", () => {
  it("includes name, trigger, and action but not is_active", () => {
    const payload = buildUpdatePayload({
      name: "Renamed",
      description: "",
      triggerType: "no_show",
      actionType: "send_sms",
    });
    expect(payload).toEqual({
      name: "Renamed",
      description: undefined,
      trigger_type: "no_show",
      actions: [{ type: "send_sms", config: {} }],
    });
    expect("is_active" in payload).toBe(false);
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
