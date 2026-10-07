import { apiGet, apiPost } from "@/lib/api";
import { createApiClient, type FullApiClient } from "@/lib/api/create-api-client";
import type { Appointment } from "@/types";

// Request/Response Types
export interface AppointmentsListParams {
  page?: number;
  page_size?: number;
  status_filter?: string;
  contact_id?: number;
  agent_id?: string;
  date_from?: string; // ISO datetime string
  date_to?: string; // ISO datetime string
}

export interface AppointmentsListResponse {
  items: Appointment[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface UpdateAppointmentRequest {
  status?: "scheduled" | "completed" | "cancelled" | "no_show";
  duration_minutes?: number;
  service_type?: string;
  notes?: string;
}

export interface CreateAppointmentRequest {
  contact_id: number;
  agent_id?: string;
  scheduled_at: string;
  duration_minutes?: number;
  service_type?: string;
  notes?: string;
}

// ---------------------------------------------------------------------------
// Show-up rate analytics types
// ---------------------------------------------------------------------------

export interface AppointmentOverallStats {
  total: number;
  scheduled: number;
  completed: number;
  no_show: number;
  cancelled: number;
  show_up_rate: number;
}

export interface AppointmentAgentStat {
  agent_id: string;
  agent_name: string;
  total: number;
  completed: number;
  no_show: number;
  show_up_rate: number;
}

export interface AppointmentCampaignStat {
  campaign_id: string;
  campaign_name: string;
  total: number;
  completed: number;
  no_show: number;
  show_up_rate: number;
}

export interface AppointmentStatsResponse {
  overall: AppointmentOverallStats;
  by_agent: AppointmentAgentStat[];
  by_campaign: AppointmentCampaignStat[];
}

// Appointments API
const baseApi = createApiClient<
  Appointment,
  CreateAppointmentRequest,
  UpdateAppointmentRequest
>({
  resourcePath: "appointments",
}) as FullApiClient<Appointment, CreateAppointmentRequest, UpdateAppointmentRequest>;

/**
 * Result of a manual reminder send. `success` means the SMS provider accepted
 * the message (or already had) — not that the carrier delivered it.
 */
export interface SendReminderResult {
  success: boolean;
  status?: "sent" | "already_sent" | "failed" | "not_sent";
  message: string;
  sent_to: string | null;
  /** True when pressing send again can make a fresh attempt. */
  retryable?: boolean;
}

export interface CancelAppointmentRequest {
  reason?: string;
  /** Mark cancelled in the CRM only; the external booking stays active. */
  crm_only?: boolean;
}

/** Honest outcome of a cancel: what happened in the CRM and on Cal.com. */
export interface CancelAppointmentResult {
  appointment: Appointment;
  outcome: "cancelled" | "already_cancelled";
  provider: "calcom" | "none";
  provider_result:
    | "cancelled"
    | "already_cancelled"
    | "not_found"
    | "skipped"
    | "not_applicable";
  /** "provider": Cal.com sent its own notice. The CRM never messages on cancel. */
  attendee_notice: "provider" | "none";
  message: string;
}

export const appointmentsApi = {
  ...baseApi,

  /**
   * Cancel an appointment, cancelling its Cal.com booking first.
   * POST /api/v1/workspaces/{workspaceId}/appointments/{appointmentId}/cancel
   * Fails with 502 `calendar_cancel_failed` (nothing changed) when Cal.com does not cancel.
   */
  cancel: async (
    workspaceId: string,
    appointmentId: number,
    data: CancelAppointmentRequest
  ): Promise<CancelAppointmentResult> => {
    return apiPost<CancelAppointmentResult>(
      `/api/v1/workspaces/${workspaceId}/appointments/${appointmentId}/cancel`,
      data
    );
  },

  /**
   * Retry Cal.com sync for a pending appointment.
   * POST /api/v1/workspaces/{workspaceId}/appointments/{appointmentId}/sync
   */
  syncAppointment: async (
    workspaceId: string,
    appointmentId: number
  ): Promise<{ status: string; error?: string }> => {
    return apiPost<{ status: string; error?: string }>(
      `/api/v1/workspaces/${workspaceId}/appointments/${appointmentId}/sync`
    );
  },

  /**
   * Fetch show-up rate analytics for a workspace.
   * GET /api/v1/workspaces/{workspaceId}/appointments/stats
   */
  getStats: async (workspaceId: string): Promise<AppointmentStatsResponse> => {
    return apiGet<AppointmentStatsResponse>(
      `/api/v1/workspaces/${workspaceId}/appointments/stats`
    );
  },

  /**
   * Manually send an SMS reminder for a scheduled appointment.
   * POST /api/v1/workspaces/{workspaceId}/appointments/{appointmentId}/send-reminder
   */
  sendReminder: async (
    workspaceId: string,
    appointmentId: number
  ): Promise<SendReminderResult> => {
    return apiPost<SendReminderResult>(
      `/api/v1/workspaces/${workspaceId}/appointments/${appointmentId}/send-reminder`
    );
  },
};
