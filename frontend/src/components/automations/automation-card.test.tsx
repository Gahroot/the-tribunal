import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Automation } from "@/types";

import { AutomationCard } from "./automation-card";

function makeAutomation(overrides: Partial<Automation> = {}): Automation {
  return {
    id: "auto-1",
    name: "New Lead Welcome",
    description: "Greets every new lead",
    trigger_type: "appointment_booked",
    trigger_config: {},
    actions: [{ type: "send_email", config: {} }],
    is_active: true,
    last_triggered_at: undefined,
    created_at: "2026-06-01T00:00:00.000Z",
    updated_at: "2026-06-10T00:00:00.000Z",
    readiness: "ready",
    config_issues: [],
    last_execution: null,
    ...overrides,
  };
}

function renderCard(
  automation: Automation = makeAutomation(),
  props: Partial<React.ComponentProps<typeof AutomationCard>> = {},
) {
  const handlers = {
    onConfigure: vi.fn(),
    onToggle: vi.fn(),
    onDuplicate: vi.fn(),
    onDelete: vi.fn(),
  };
  render(
    <AutomationCard
      automation={automation}
      isToggling={false}
      isDuplicating={false}
      isDeleting={false}
      {...handlers}
      {...props}
    />,
  );
  return handlers;
}

describe("AutomationCard", () => {
  it("renders the resolved trigger and action labels", () => {
    renderCard();
    expect(screen.getByText("New Lead Welcome")).toBeInTheDocument();
    expect(screen.getByText("Appointment Booked Trigger")).toBeInTheDocument();
    expect(screen.getByText("Send Email")).toBeInTheDocument();
  });

  it("falls back to a generic label for unknown trigger types", () => {
    renderCard(
      makeAutomation({
        trigger_type: "totally_custom" as Automation["trigger_type"],
      }),
    );
    expect(screen.getByText("totally_custom Trigger")).toBeInTheDocument();
  });

  it("shows 'Never triggered' when there is no last run", () => {
    renderCard();
    expect(screen.getByText("Never triggered")).toBeInTheDocument();
  });

  it("fires onToggle when the footer switch is flipped", () => {
    const { onToggle } = renderCard();
    fireEvent.click(screen.getByRole("switch"));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("marks an incomplete automation as needing setup with its issues", () => {
    const { onConfigure } = renderCard(
      makeAutomation({
        is_active: false,
        readiness: "incomplete",
        config_issues: [
          {
            code: "missing_sms_message",
            field: "actions[0].config.message",
            message: "Step 1: write the text message to send.",
          },
        ],
      }),
    );
    expect(screen.getByText("Needs setup")).toBeInTheDocument();
    expect(
      screen.getByText("Step 1: write the text message to send."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Configure" }));
    expect(onConfigure).toHaveBeenCalledTimes(1);
  });

  it("shows the actionable error from a failed run", () => {
    renderCard(
      makeAutomation({
        last_execution: {
          id: "e1",
          status: "failed",
          error: "No SMS-enabled phone number is active in this workspace.",
          contact_id: 7,
          created_at: "2026-06-12T00:00:00.000Z",
          executed_at: "2026-06-12T00:00:01.000Z",
        },
      }),
    );
    expect(screen.getAllByText("Last run failed").length).toBeGreaterThan(0);
    expect(
      screen.getByText("No SMS-enabled phone number is active in this workspace."),
    ).toBeInTheDocument();
  });

  it("shows the ready state for an active, never-run automation", () => {
    renderCard();
    expect(screen.getByText("Ready")).toBeInTheDocument();
  });
});
