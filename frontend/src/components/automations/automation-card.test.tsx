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
});
