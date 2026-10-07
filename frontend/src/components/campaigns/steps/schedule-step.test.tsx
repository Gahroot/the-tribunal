import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { ReviewScheduleCard } from "@/components/campaigns/steps/review-schedule-card";
import { ScheduleStep } from "@/components/campaigns/steps/schedule-step";

function Harness({ onSaved }: { onSaved: (days: number[]) => void }) {
  const [days, setDays] = useState<number[]>([]);
  return (
    <>
      <ScheduleStep
        sendingHoursEnabled={false}
        sendingHoursStart="09:00"
        sendingHoursEnd="17:00"
        sendingDays={days}
        timezone="America/New_York"
        errors={{}}
        onScheduledStartChange={() => {}}
        onScheduledEndChange={() => {}}
        onSendingHoursEnabledChange={() => {}}
        onSendingHoursStartChange={() => {}}
        onSendingHoursEndChange={() => {}}
        onSendingDaysChange={(next) => {
          setDays(next);
          onSaved(next);
        }}
        onTimezoneChange={() => {}}
      />
      <ReviewScheduleCard
        sendingHoursEnabled={false}
        sendingHoursStart="09:00"
        sendingHoursEnd="17:00"
        sendingDays={days}
        timezone="America/New_York"
        rateDescription="10 / minute"
      />
    </>
  );
}

describe("ScheduleStep day picker (RF-006)", () => {
  it("saves Monday–Friday as backend weekday values and reviews the same days", () => {
    let saved: number[] = [];
    render(<Harness onSaved={(d) => (saved = d)} />);

    // Click out of order to prove values are normalised numerically.
    for (const label of ["Fri", "Mon", "Wed", "Tue", "Thu"]) {
      fireEvent.click(screen.getByRole("button", { name: label }));
    }

    expect(saved).toEqual([0, 1, 2, 3, 4]);
    expect(screen.getByRole("button", { name: "Sat" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(screen.getByRole("button", { name: "Sun" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(screen.getByText("Mon, Tue, Wed, Thu, Fri")).toBeInTheDocument();
  });

  it("saves a weekend-only schedule as Saturday=5, Sunday=6", () => {
    let saved: number[] = [];
    render(<Harness onSaved={(d) => (saved = d)} />);
    fireEvent.click(screen.getByRole("button", { name: "Sun" }));
    fireEvent.click(screen.getByRole("button", { name: "Sat" }));
    expect(saved).toEqual([5, 6]);
    expect(screen.getByText("Sat, Sun")).toBeInTheDocument();
  });
});
