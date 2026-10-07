"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Clock, Loader2, Mail, RotateCw, X } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { invitationsApi, type InvitationResponse } from "@/lib/api/invitations";
import { useResendInvitation } from "@/lib/invitations/delivery";
import { queryKeys } from "@/lib/query-keys";
import { formatDate } from "@/lib/utils/date";
import { getApiErrorMessage } from "@/lib/utils/errors";

function DeliveryBadge({ invitation }: { invitation: InvitationResponse }) {
  if (invitation.is_expired) {
    return <Badge variant="destructive">Expired</Badge>;
  }
  switch (invitation.email_status) {
    case "sent":
      return <Badge variant="secondary">Email sent</Badge>;
    case "failed":
      return <Badge variant="destructive">Email failed</Badge>;
    case "not_configured":
      return <Badge variant="destructive">Email not sent</Badge>;
    default:
      return null;
  }
}

interface TeamInviteFormProps {
  workspaceId: string | null;
}

/**
 * Pending invitations card.
 *
 * Renders the list of outstanding workspace invitations and exposes a per-row
 * resend/cancel actions with each invitation's real email delivery status.
 * The "send invitation" form itself lives in
 * `InviteMemberDialog` (already RHF-driven); this component focuses purely on
 * the pending-list surface so TeamSettingsTab stays small.
 */
export function TeamInviteForm({ workspaceId }: TeamInviteFormProps) {
  const queryClient = useQueryClient();

  const { data: pendingInvitations, isPending: invitationsLoading } = useQuery({
    queryKey: queryKeys.invitations.all(workspaceId ?? ""),
    queryFn: () => invitationsApi.list(workspaceId!),
    enabled: !!workspaceId,
  });

  const resendInvitationMutation = useResendInvitation(workspaceId);

  const cancelInvitationMutation = useMutation({
    mutationFn: (invitationId: string) =>
      invitationsApi.cancel(workspaceId!, invitationId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.invitations.all(workspaceId ?? ""),
      });
      toast.success("Invitation cancelled");
    },
    onError: (err: unknown) => {
      toast.error(getApiErrorMessage(err, "Failed to cancel invitation"));
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Clock className="size-5" />
          Pending Invitations
        </CardTitle>
        <CardDescription>Invitations waiting to be accepted</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {invitationsLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="size-6 animate-spin text-muted-foreground" />
          </div>
        ) : pendingInvitations && pendingInvitations.length > 0 ? (
          pendingInvitations.map((invitation) => (
            <div
              key={invitation.id}
              className="flex items-center justify-between p-3 rounded-lg border"
            >
              <div className="flex items-center gap-3">
                <div className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
                  <Mail className="size-5" />
                </div>
                <div>
                  <p className="font-medium">{invitation.email}</p>
                  <p className="text-sm text-muted-foreground">
                    Invited {formatDate(invitation.created_at)}
                    {" · "}
                    {invitation.is_expired ? "Expired" : "Expires"}{" "}
                    {formatDate(invitation.expires_at)}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <DeliveryBadge invitation={invitation} />
                <Badge variant="outline" className="capitalize">
                  {invitation.role}
                </Badge>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Resend invitation to ${invitation.email}`}
                  title="Resend invitation email"
                  onClick={() => resendInvitationMutation.mutate(invitation.id)}
                  disabled={resendInvitationMutation.isPending}
                >
                  {resendInvitationMutation.isPending &&
                  resendInvitationMutation.variables === invitation.id ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <RotateCw className="size-4" />
                  )}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Cancel invitation to ${invitation.email}`}
                  title="Cancel invitation"
                  onClick={() => cancelInvitationMutation.mutate(invitation.id)}
                  disabled={cancelInvitationMutation.isPending}
                >
                  <X className="size-4" />
                </Button>
              </div>
            </div>
          ))
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            No pending invitations
          </div>
        )}
      </CardContent>
    </Card>
  );
}
