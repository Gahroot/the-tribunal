"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { invitationsApi, type InvitationResponse } from "@/lib/api/invitations";
import { queryKeys } from "@/lib/query-keys";
import { getApiErrorMessage } from "@/lib/utils/errors";

/**
 * Report the real email delivery outcome of a created or resent invitation.
 * Only `email_status === "sent"` is shown as success; anything else tells the
 * admin the invitation is saved but the recipient has not been emailed.
 */
export function showInvitationDeliveryToast(
  invitation: InvitationResponse,
  onResend?: () => void,
) {
  const action = onResend ? { label: "Resend", onClick: onResend } : undefined;

  switch (invitation.email_status) {
    case "sent":
      toast.success(`Invitation emailed to ${invitation.email}`);
      return;
    case "not_configured":
      toast.warning(`Invitation saved, but no email was sent to ${invitation.email}`, {
        description:
          "Email delivery isn't set up for this app yet. Resend it from Pending Invitations once email is configured.",
        duration: 10000,
      });
      return;
    default:
      toast.error(`Invitation saved, but the email to ${invitation.email} didn't send`, {
        description: "Use Resend to try again. No duplicate invitation will be created.",
        duration: 10000,
        action,
      });
  }
}

/** Resend an existing invitation's email and report the real outcome. */
export function useResendInvitation(workspaceId: string | null) {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (invitationId: string) => invitationsApi.resend(workspaceId!, invitationId),
    onSuccess: (invitation) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.invitations.all(workspaceId ?? ""),
      });
      showInvitationDeliveryToast(invitation, () => {
        mutation.mutate(invitation.id);
      });
    },
    onError: (err: unknown) => {
      toast.error(getApiErrorMessage(err, "Failed to resend invitation"));
    },
  });

  return mutation;
}
