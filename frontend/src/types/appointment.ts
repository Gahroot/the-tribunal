// Appointment and Cal.com Integration Types

import type { Contact } from "./contact";

export interface Appointment {
  id: number;
  contact_id: number;
  contact?: Contact;
  workspace_id?: string;
  agent_id?: string;
  message_id?: string;
  campaign_id?: string;
  scheduled_at: string;
  duration_minutes: number;
  status: "scheduled" | "completed" | "cancelled" | "no_show";
  service_type?: string;
  notes?: string;
  calcom_booking_uid?: string;
  calcom_booking_id?: number;
  calcom_event_type_id?: number;
  sync_status?: string;
  last_synced_at?: string;
  sync_error?: string;
  created_at: string;
  updated_at: string;
  reminder_sent_at?: string;
  reminders_sent?: number[];
}

export interface CalcomConfig {
  id: string;
  user_id: number;
  workspace_id?: string;
  api_key: string;
  event_type_id: number;
  event_type_slug: string;
  calendar_id?: string;
  default_duration_minutes: number;
  buffer_before_minutes?: number;
  buffer_after_minutes?: number;
  booking_questions?: CalcomBookingQuestion[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CalcomBookingQuestion {
  name: string;
  type: "text" | "textarea" | "select" | "multiselect" | "phone" | "email";
  label: string;
  required: boolean;
  options?: string[];
}

export interface CalcomBooking {
  id: number;
  uid: string;
  user_id: number;
  contact_id: number;
  event_type_id: number;
  title: string;
  description?: string;
  start_time: string;
  end_time: string;
  timezone: string;
  status: "accepted" | "pending" | "cancelled" | "rejected";
  location?: string;
  meeting_url?: string;
  attendees: CalcomAttendee[];
  metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface CalcomAttendee {
  email: string;
  name: string;
  phone?: string;
  timezone: string;
}

export interface CalcomAvailability {
  date: string;
  slots: CalcomTimeSlot[];
}

export interface CalcomTimeSlot {
  start: string;
  end: string;
  available: boolean;
}
