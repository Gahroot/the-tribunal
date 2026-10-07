import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { InboundAgentControl } from "@/components/settings/phone-numbers-views";
import { describePurchaseOutcome } from "@/hooks/usePhoneNumberManager";
import type {
  EligibleVoiceAgent,
  PhoneNumberInboundReadiness,
  PhoneNumberPurchaseResult,
} from "@/lib/api/phone-numbers";
import type { PhoneNumber } from "@/types";

const number: PhoneNumber = {
  id: "pn-1",
  workspace_id: "ws-1",
  phone_number: "+15551230000",
  sms_enabled: true,
  voice_enabled: true,
  mms_enabled: false,
  is_active: true,
};

function readiness(overrides: Partial<PhoneNumberInboundReadiness>): PhoneNumberInboundReadiness {
  return {
    phone_number_id: "pn-1",
    status: "needs_agent_choice",
    ready: false,
    assigned_agent_id: null,
    assigned_agent_name: null,
    eligible_agent_count: 0,
    message: "No agent is assigned, so inbound calls go to voicemail. Choose a voice agent.",
    action_label: null,
    action_href: null,
    ...overrides,
  };
}

const agents: EligibleVoiceAgent[] = [
  { id: "a-1", name: "Sales", channel_mode: "voice" },
  { id: "a-2", name: "Support", channel_mode: "both" },
];

function renderControl(r: PhoneNumberInboundReadiness, eligible: EligibleVoiceAgent[]) {
  return render(
    <InboundAgentControl
      number={number}
      readiness={r}
      eligibleAgents={eligible}
      isAssigning={false}
      onAssignAgent={vi.fn()}
    />,
  );
}

describe("InboundAgentControl", () => {
  it("shows the recovery link when no eligible voice agent exists", () => {
    renderControl(
      readiness({
        status: "no_eligible_agent",
        message: "No active voice agent exists, so inbound calls go to voicemail.",
        action_label: "Create a voice agent",
        action_href: "/agents/create",
      }),
      [],
    );

    expect(screen.getByText("Calls go to voicemail")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create a voice agent" })).toHaveAttribute(
      "href",
      "/agents/create",
    );
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });

  it("requires an explicit choice when several agents are eligible", () => {
    renderControl(readiness({ eligible_agent_count: 2 }), agents);

    expect(screen.getByText("Calls go to voicemail")).toBeInTheDocument();
    expect(
      screen.getByRole("combobox", { name: /Agent that answers calls to/ }),
    ).toHaveTextContent("Choose agent to answer calls");
  });

  it("shows the answering agent when ready", () => {
    renderControl(
      readiness({
        status: "ready",
        ready: true,
        assigned_agent_id: "a-1",
        assigned_agent_name: "Sales",
        eligible_agent_count: 1,
      }),
      [agents[0]],
    );

    expect(screen.getByText("Calls answered by Sales")).toBeInTheDocument();
    expect(screen.queryByText("Calls go to voicemail")).not.toBeInTheDocument();
  });

  it("renders nothing for SMS-only numbers", () => {
    const { container } = renderControl(readiness({ status: "voice_disabled" }), agents);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("describePurchaseOutcome", () => {
  const base = {
    ...number,
    friendly_name: null,
    provider: "telnyx",
    imessage_enabled: false,
    mac_relay_sender_id: null,
    mac_relay_service: "imessage",
    assigned_agent_id: null,
  } satisfies Omit<PhoneNumberPurchaseResult, "agent_assignment" | "inbound_voice">;

  it("confirms the default agent when one was auto-assigned", () => {
    const outcome = describePurchaseOutcome({
      ...base,
      assigned_agent_id: "a-1",
      agent_assignment: "default_single_agent",
      inbound_voice: readiness({ status: "ready", ready: true, assigned_agent_name: "Sales" }),
    });
    expect(outcome).toEqual({
      kind: "success",
      message: "Purchased +15551230000. Inbound calls are answered by Sales.",
    });
  });

  it("warns when the assignment is still pending", () => {
    const outcome = describePurchaseOutcome({
      ...base,
      agent_assignment: "pending",
      inbound_voice: readiness({ eligible_agent_count: 2 }),
    });
    expect(outcome.kind).toBe("warning");
    expect(outcome.message).toContain("Choose a voice agent");
  });
});
