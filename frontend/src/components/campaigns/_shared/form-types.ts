/**
 * Field fragments and initial values shared by SMS and Voice campaign
 * wizards. The wizards extend these with channel-specific fields.
 */

export interface BasicsFields {
  name: string;
  description: string;
  from_phone_number: string;
}

export interface ScheduleFields {
  scheduled_start?: string;
  scheduled_end?: string;
  sending_hours_enabled: boolean;
  sending_hours_start: string;
  sending_hours_end: string;
  sending_days: number[];
  timezone: string;
}

export const initialBasicsFields: BasicsFields = {
  name: "",
  description: "",
  from_phone_number: "",
};

export const initialScheduleFields: ScheduleFields = {
  sending_hours_enabled: false,
  sending_hours_start: "09:00",
  sending_hours_end: "17:00",
  sending_days: [1, 2, 3, 4, 5],
  timezone: "America/New_York",
};

export interface ScheduleRequestFields {
  scheduled_start?: string;
  scheduled_end?: string;
  sending_hours_start: string;
  sending_hours_end: string;
  sending_days: number[];
  timezone: string;
}

/**
 * Normalises schedule form data into the request shape consumed by the
 * SMS/Voice campaign create endpoints. When sending hours are disabled
 * the window collapses to the full 24h day.
 */
export function mapScheduleToRequest(
  data: ScheduleFields,
): ScheduleRequestFields {
  return {
    scheduled_start: data.scheduled_start || undefined,
    scheduled_end: data.scheduled_end || undefined,
    sending_hours_start: data.sending_hours_enabled
      ? data.sending_hours_start
      : "00:00",
    sending_hours_end: data.sending_hours_enabled
      ? data.sending_hours_end
      : "23:59",
    sending_days: data.sending_days,
    timezone: data.timezone,
  };
}
