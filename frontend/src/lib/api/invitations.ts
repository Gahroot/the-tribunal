import { apiGet, apiPost, apiDelete } from "@/lib/api";

/**
 * Email delivery outcome, separate from the invitation lifecycle `status`.
 * "sent" = the email provider accepted the message. "failed" and
 * "not_configured" mean the invitation exists but was never emailed.
 * "unknown" = created before delivery was tracked.
 */
export type InvitationEmailStatus = "sent" | "failed" | "not_configured" | "unknown";

export interface InvitationResponse {
  id: string;
  workspace_id: string;
  email: string;
  role: string;
  status: string;
  message: string | null;
  invited_by_email: string | null;
  invited_by_name: string | null;
  expires_at: string;
  created_at: string;
  accepted_at: string | null;
  is_expired: boolean;
  email_status: InvitationEmailStatus;
  email_attempt_count: number;
  email_last_attempt_at: string | null;
  email_sent_at: string | null;
}

export interface InvitationPublicResponse {
  workspace_name: string;
  workspace_slug: string;
  email: string;
  role: string;
  invited_by_name: string | null;
  expires_at: string;
  is_expired: boolean;
  is_valid: boolean;
}

export interface InvitationAcceptResponse {
  success: boolean;
  message: string;
  workspace_id: string | null;
  workspace_slug: string | null;
}

export interface CreateInvitationRequest {
  email: string;
  role: "admin" | "member";
  message?: string;
}

/**
 * Invitations API.
 *
 * Note: This API is NOT fully migrated to use the factory because:
 * 1. The list endpoint returns an array, not a paginated response
 * 2. The API has mixed scoping - list/create/cancel are workspace-scoped,
 *    but getByToken and accept are public (non-workspace-scoped) endpoints
 *
 * The factory pattern expects paginated list responses and consistent scoping,
 * which this API doesn't have. Keeping the original implementation.
 */
export const invitationsApi = {
  /**
   * List pending invitations for a workspace (admin only)
   * Note: Returns a plain array, not paginated, to match backend API
   */
  list: async (workspaceId: string): Promise<InvitationResponse[]> => {
    return apiGet<InvitationResponse[]>(
      `/api/v1/workspaces/${workspaceId}/invitations`
    );
  },

  /**
   * Create an invitation and attempt to email it. Check `email_status` on the
   * result: a 201 does not by itself mean the email was sent.
   */
  create: async (
    workspaceId: string,
    data: CreateInvitationRequest
  ): Promise<InvitationResponse> => {
    return apiPost<InvitationResponse>(
      `/api/v1/workspaces/${workspaceId}/invitations`,
      data
    );
  },

  /**
   * Retry email delivery for an existing pending invitation (no duplicate is
   * created). Check `email_status` on the result.
   */
  resend: async (workspaceId: string, invitationId: string): Promise<InvitationResponse> => {
    return apiPost<InvitationResponse>(
      `/api/v1/workspaces/${workspaceId}/invitations/${invitationId}/resend`
    );
  },

  /**
   * Cancel a pending invitation
   */
  cancel: async (workspaceId: string, invitationId: string): Promise<void> => {
    await apiDelete(`/api/v1/workspaces/${workspaceId}/invitations/${invitationId}`);
  },

  /**
   * Get invitation details by token (public endpoint - NOT workspace-scoped)
   */
  getByToken: async (token: string): Promise<InvitationPublicResponse> => {
    return apiGet<InvitationPublicResponse>(
      `/api/v1/invitations/${encodeURIComponent(token)}`
    );
  },

  /**
   * Accept an invitation (must be logged in - NOT workspace-scoped).
   * A lapsed session rejects with 401 instead of hard-redirecting to /login,
   * so the invite page can send the user to sign in and come back.
   */
  accept: async (token: string): Promise<InvitationAcceptResponse> => {
    return apiPost<InvitationAcceptResponse>(
      `/api/v1/invitations/${encodeURIComponent(token)}/accept`,
      undefined,
      { skipAuthRedirect: true }
    );
  },
};
