import type { Campaign } from "@/types";

// Legacy offset-free database timestamps are UTC, never the browser's timezone.
function instant(value: string): Date {
  return new Date(/[zZ]$|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
}

type Schedule = Pick<
  Campaign,
  | "status"
  | "scheduled_start"
  | "scheduled_end"
  | "sending_hours_start"
  | "sending_hours_end"
  | "sending_days"
  | "timezone"
>;

/** Timing estimate only. Consent, quiet hours, rate limits and providers still gate delivery. */
export function futureCampaignStart(schedule: Schedule, now = new Date()): string | null {
  if (schedule.status !== "running" && schedule.status !== "scheduled") return null;
  if (!schedule.scheduled_start) return null;
  const start = instant(schedule.scheduled_start);
  if (!Number.isFinite(start.getTime()) || start <= now) return null;
  const timeZone = schedule.timezone || "UTC";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  });
  const local = (date: Date): number => {
    const p = Object.fromEntries(parts.formatToParts(date).map(({ type, value }) => [type, value]));
    return Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second);
  };
  let next: Date | null = start;
  if (schedule.sending_hours_start && schedule.sending_hours_end) {
    next = null;
    const earliestLocal = local(start) + start.getUTCMilliseconds();
    const day = new Date(earliestLocal);
    day.setUTCHours(0, 0, 0, 0);
    const clock = (value: string): number => {
      const [h, m, s = 0] = value.split(":").map(Number);
      return ((h * 60 + m) * 60 + s) * 1000;
    };
    const from = clock(schedule.sending_hours_start);
    const to = clock(schedule.sending_hours_end);
    // A weekly window has a candidate within eight local dates. No polling or timers.
    for (let offset = 0; offset < 8; offset++) {
      const date = new Date(day.getTime() + offset * 86400000);
      if (schedule.sending_days?.length && !schedule.sending_days.includes((date.getUTCDay() + 6) % 7))
        continue;
      const target = Math.max(date.getTime() + from, earliestLocal);
      if (target > date.getTime() + to) continue;
      let candidate = target === earliestLocal ? start : new Date(target);
      for (let i = 0; i < 3; i++)
        candidate = new Date(candidate.getTime() + target - local(candidate) - candidate.getUTCMilliseconds());
      // Skip nonexistent DST wall times rather than promise an illegal sending slot.
      if (local(candidate) + candidate.getUTCMilliseconds() !== target || candidate < start) continue;
      next = candidate;
      break;
    }
  }
  if (!next || (schedule.scheduled_end && next > instant(schedule.scheduled_end))) {
    return "No eligible sending window before the scheduled end";
  }
  return `Next eligible start: ${new Intl.DateTimeFormat("en-US", {
    timeZone,
    dateStyle: "medium",
    timeStyle: "short",
  }).format(next)} (${timeZone}). Recipient safeguards still apply.`;
}
