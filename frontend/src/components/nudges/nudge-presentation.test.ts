import { Cake, Hourglass, Pin } from "lucide-react";
import { describe, expect, it } from "vitest";

import { formatDueDate, getNudgeIcon } from "./nudge-presentation";

describe("getNudgeIcon", () => {
  it("maps known nudge types to their icon", () => {
    expect(getNudgeIcon("birthday")).toBe(Cake);
    expect(getNudgeIcon("approvals_waiting")).toBe(Hourglass);
  });

  it("falls back to a generic pin for unknown types", () => {
    expect(getNudgeIcon("totally_unknown")).toBe(Pin);
  });
});

describe("formatDueDate", () => {
  const now = new Date("2026-06-15T12:00:00.000Z");
  const daysFromNow = (days: number) =>
    new Date(now.getTime() + days * 24 * 60 * 60 * 1000).toISOString();

  it("labels today, tomorrow, and yesterday", () => {
    expect(formatDueDate(daysFromNow(0), now)).toBe("Today");
    expect(formatDueDate(daysFromNow(1), now)).toBe("Tomorrow");
    expect(formatDueDate(daysFromNow(-1), now)).toBe("Yesterday");
  });

  it("buckets the next two weeks as 'In N days'", () => {
    expect(formatDueDate(daysFromNow(3), now)).toBe("In 3 days");
    expect(formatDueDate(daysFromNow(14), now)).toBe("In 14 days");
  });

  it("buckets the previous two weeks as 'N days ago'", () => {
    expect(formatDueDate(daysFromNow(-5), now)).toBe("5 days ago");
    expect(formatDueDate(daysFromNow(-14), now)).toBe("14 days ago");
  });

  it("defers to relative formatting beyond two weeks", () => {
    const result = formatDueDate(daysFromNow(30), now);
    expect(result).not.toMatch(/^In \d+ days$/);
    expect(result).not.toBe("Today");
  });
});
