import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CampaignStatusBadge } from "@/components/campaigns/campaign-status-badge";
import { futureCampaignStart } from "@/lib/campaign-schedule";
import type { Campaign } from "@/types";

const schedule = {
  status: "running",
  scheduled_start: "2026-10-09T18:00:00Z",
  sending_hours_start: "09:00:00",
  sending_hours_end: "17:00:00",
  sending_days: [0, 1, 2, 3, 4],
  timezone: "America/New_York",
} as Campaign;

afterEach(() => vi.useRealTimers());

describe("future-scheduled campaign status", () => {
  it("shows Scheduled and a timezone-qualified next start, not Running", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-08T12:00:00Z"));
    render(<CampaignStatusBadge status="running" schedule={schedule} />);
    expect(screen.getByText("Scheduled")).toBeInTheDocument();
    expect(screen.queryByText("Running")).not.toBeInTheDocument();
    expect(screen.getByText(/Next eligible start: Oct 9, 2026, 2:00 PM/)).toHaveTextContent(
      "America/New_York",
    );
  });

  it.each([0, 1])("does not claim a future schedule at/after start (%i seconds)", (offset) => {
    const now = new Date(new Date(schedule.scheduled_start!).getTime() + offset * 1000);
    expect(futureCampaignStart(schedule, now)).toBeNull();
  });

  it("moves a Friday evening start to Monday morning in campaign timezone", () => {
    expect(
      futureCampaignStart(
        { ...schedule, scheduled_start: "2026-10-09T22:00:00Z" },
        new Date("2026-10-08Z"),
      ),
    ).toContain("Oct 12, 2026, 9:00 AM");
  });

  it("keeps paused campaigns paused and respects the scheduled end", () => {
    const now = new Date("2026-10-08T12:00:00Z");
    expect(futureCampaignStart({ ...schedule, status: "paused" }, now)).toBeNull();
    expect(futureCampaignStart({ ...schedule, scheduled_end: "2026-10-09T17:00:00Z" }, now)).toBe(
      "No eligible sending window before the scheduled end",
    );
  });

  it("preserves legacy empty sending days and fractional start instants", () => {
    expect(futureCampaignStart({
      ...schedule, sending_days: [], scheduled_start: "2026-10-10T14:00:00.500Z",
    }, new Date("2026-10-08T12:00:00Z"))).toContain("Oct 10, 2026, 10:00 AM");
  });

  it("handles DST and legacy naive UTC timestamps", () => {
    const now = new Date("2026-10-30T12:00:00Z");
    expect(
      futureCampaignStart({ ...schedule, scheduled_start: "2026-10-30T22:00:00" }, now),
    ).toContain("Nov 2, 2026, 9:00 AM");
  });
});
