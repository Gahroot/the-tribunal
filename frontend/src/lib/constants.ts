/**
 * Shared constants used across the application
 */

// Timezone options with display labels (for Select components)
export const TIMEZONE_OPTIONS = [
  { value: "America/New_York", label: "America/New York (EST)" },
  { value: "America/Chicago", label: "America/Chicago (CST)" },
  { value: "America/Denver", label: "America/Denver (MST)" },
  { value: "America/Los_Angeles", label: "America/Los Angeles (PST)" },
  { value: "America/Phoenix", label: "America/Phoenix (MST)" },
  { value: "Pacific/Honolulu", label: "Pacific/Honolulu (HST)" },
  { value: "Europe/London", label: "Europe/London (GMT)" },
  { value: "Europe/Paris", label: "Europe/Paris (CET)" },
  { value: "Asia/Tokyo", label: "Asia/Tokyo (JST)" },
  { value: "Australia/Sydney", label: "Australia/Sydney (AEST)" },
] as const;

// Simple timezone list (for forms that just need values)
export const TIMEZONES = TIMEZONE_OPTIONS.map((tz) => tz.value);

/**
 * Campaign `sending_days` encoding — must match the backend contract in
 * `backend/app/core/sending_days.py`: Python `weekday()` values evaluated in
 * the campaign timezone, Monday=0 … Sunday=6. This is NOT `Date.getDay()`
 * (Sunday=0); never feed `getDay()` results into `sending_days`.
 */
export const DAYS_OF_WEEK = [
  { value: 0, label: "Mon" },
  { value: 1, label: "Tue" },
  { value: 2, label: "Wed" },
  { value: 3, label: "Thu" },
  { value: 4, label: "Fri" },
  { value: 5, label: "Sat" },
  { value: 6, label: "Sun" },
] as const;

/** Monday–Friday in the shared Monday=0 encoding. */
export const WEEKDAY_SENDING_DAYS: readonly number[] = [0, 1, 2, 3, 4];

/** Sorted, de-duplicated day values (numeric order, Monday first). */
export function normalizeSendingDays(days: readonly number[]): number[] {
  return Array.from(new Set(days)).sort((a, b) => a - b);
}

/** Human labels for stored `sending_days`, e.g. "Mon, Tue, Wed". */
export function formatSendingDays(days: readonly number[]): string {
  return normalizeSendingDays(days)
    .map((d) => DAYS_OF_WEEK.find((day) => day.value === d)?.label)
    .filter(Boolean)
    .join(", ");
}
