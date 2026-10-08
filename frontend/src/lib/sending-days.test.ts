import { describe, expect, it } from "vitest";

import {
  initialScheduleFields,
  mapScheduleToRequest,
} from "@/components/campaigns/_shared/form-types";
import {
  DAYS_OF_WEEK,
  formatSendingDays,
  normalizeSendingDays,
  WEEKDAY_SENDING_DAYS,
} from "@/lib/constants";

// RF-006: backend contract is Python weekday() — Monday=0 … Sunday=6
// (backend/app/core/sending_days.py). Not JavaScript getDay().
const PYTHON_WEEKDAY: Record<string, number> = {
  Mon: 0,
  Tue: 1,
  Wed: 2,
  Thu: 3,
  Fri: 4,
  Sat: 5,
  Sun: 6,
};

describe("sending_days encoding", () => {
  it.each(Object.entries(PYTHON_WEEKDAY))(
    "labels %s with backend weekday value %i",
    (label, value) => {
      expect(DAYS_OF_WEEK.find((d) => d.label === label)?.value).toBe(value);
    },
  );

  it("matches the backend weekday for every real calendar date", () => {
    // 2026-10-05 is a Monday; getDay() uses Sunday=0, the contract Monday=0.
    for (let offset = 0; offset < 7; offset++) {
      const date = new Date(Date.UTC(2026, 9, 5 + offset, 12));
      const label = date.toLocaleDateString("en-US", {
        weekday: "short",
        timeZone: "UTC",
      });
      const contractValue = (date.getUTCDay() + 6) % 7;
      expect(DAYS_OF_WEEK.find((d) => d.label === label)?.value).toBe(
        contractValue,
      );
    }
  });

  it("defaults new campaigns to Monday–Friday and saves them unchanged", () => {
    expect(formatSendingDays(initialScheduleFields.sending_days)).toBe(
      "Mon, Tue, Wed, Thu, Fri",
    );
    expect(mapScheduleToRequest(initialScheduleFields).sending_days).toEqual([
      0, 1, 2, 3, 4,
    ]);
    expect(WEEKDAY_SENDING_DAYS).toEqual([0, 1, 2, 3, 4]);
  });

  it("serializes local date inputs as explicit instants for both campaign channels", () => {
    const value = "2026-10-09T09:00";
    const request = mapScheduleToRequest({
      ...initialScheduleFields,
      scheduled_start: value,
      scheduled_end: value,
    });
    expect(request.scheduled_start).toBe(new Date(value).toISOString());
    expect(request.scheduled_end).toBe(new Date(value).toISOString());
    expect(request.scheduled_start).toMatch(/Z$/);
  });

  it("summarises weekend and single-day schedules in Monday-first order", () => {
    expect(formatSendingDays([6, 5])).toBe("Sat, Sun");
    expect(formatSendingDays([2])).toBe("Wed");
    expect(normalizeSendingDays([4, 0, 4, 2])).toEqual([0, 2, 4]);
  });
});
