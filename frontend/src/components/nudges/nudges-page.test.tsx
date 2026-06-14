import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NudgeCard } from "@/components/nudges/nudges-page";
import type { HumanNudge } from "@/types/nudge";

const baseNudge: HumanNudge = {
  id: "nudge-1",
  workspace_id: "workspace-1",
  contact_id: null,
  nudge_type: "approvals_waiting",
  title: "⏳ 5 approvals waiting",
  message: "Approve or reject them before they expire.",
  suggested_action: null,
  cta_label: "Review approvals",
  href: "/pending-actions",
  priority: "high",
  due_date: "2026-06-14T12:00:00.000Z",
  source_date_field: null,
  status: "pending",
  snoozed_until: null,
  delivered_via: null,
  delivered_at: null,
  acted_at: null,
  assigned_to_user_id: null,
  created_at: "2026-06-14T12:00:00.000Z",
  contact_name: null,
  contact_phone: null,
  contact_company: null,
};

function renderCard(nudge: HumanNudge = baseNudge) {
  return render(
    <NudgeCard
      nudge={nudge}
      onAct={vi.fn()}
      onDismiss={vi.fn()}
      onSnooze={vi.fn()}
      isActing={false}
      isDismissing={false}
    />,
  );
}

describe("NudgeCard CTA", () => {
  it("renders linked workspace CTAs instead of a fake Done action", () => {
    renderCard();

    const cta = screen.getByRole("link", { name: /review approvals/i });
    expect(cta).toHaveAttribute("href", "/pending-actions");
    expect(screen.queryByRole("button", { name: /done/i })).not.toBeInTheDocument();
  });
});
