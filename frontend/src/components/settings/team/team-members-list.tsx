"use client";

import { useQuery } from "@tanstack/react-query";
import { Loader2, UserPlus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { settingsApi, type TeamMember } from "@/lib/api/settings";
import { queryKeys } from "@/lib/query-keys";
import { getInitialsFromName } from "@/lib/utils/initials";

interface TeamMembersListProps {
  workspaceId: string | null;
  canEditWorkspace: boolean;
  onInvite: () => void;
  onEditMember: (member: TeamMember) => void;
}

/**
 * Members card for TeamSettingsTab.
 *
 * Owns its own React Query subscription so the parent stays focused on layout
 * + dialog plumbing. The parent only supplies workspace id, the current user's
 * permission flag, and a couple of callbacks.
 */
export function TeamMembersList({
  workspaceId,
  canEditWorkspace,
  onInvite,
  onEditMember,
}: TeamMembersListProps) {
  const { data: teamMembers, isPending: teamLoading } = useQuery({
    queryKey: queryKeys.settings.team(workspaceId ?? ""),
    queryFn: () => settingsApi.getTeamMembers(workspaceId!),
    enabled: !!workspaceId,
  });

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Team Members</CardTitle>
            <CardDescription>
              Manage who has access to your workspace
            </CardDescription>
          </div>
          {canEditWorkspace && (
            <Button onClick={onInvite}>
              <UserPlus className="mr-2 size-4" />
              Invite Member
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {teamLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="size-6 animate-spin text-muted-foreground" />
          </div>
        ) : teamMembers && teamMembers.length > 0 ? (
          teamMembers.map((member) => (
            <div
              key={member.id}
              className="flex items-center justify-between p-3 rounded-lg border"
            >
              <div className="flex items-center gap-3">
                <div className="flex size-10 items-center justify-center rounded-full bg-primary/10 text-sm font-medium">
                  {getInitialsFromName(member.full_name, member.email)}
                </div>
                <div>
                  <p className="font-medium">
                    {member.full_name || member.email}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {member.email}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Badge variant="outline" className="capitalize">
                  {member.role}
                </Badge>
                {canEditWorkspace && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onEditMember(member)}
                  >
                    Edit
                  </Button>
                )}
              </div>
            </div>
          ))
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            No team members found
          </div>
        )}
      </CardContent>
    </Card>
  );
}
