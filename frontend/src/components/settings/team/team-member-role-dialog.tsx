"use client";

import { EditMemberDialog } from "@/components/workspaces/edit-member-dialog";
import type { TeamMember } from "@/lib/api/settings";

interface TeamMemberRoleDialogProps {
  member: TeamMember | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentUserRole: string;
}

/**
 * Thin wrapper around `EditMemberDialog` that lets TeamSettingsTab open the
 * dialog with a `member | null` selection. Keeps the parent free of the "did I
 * remember to guard `selectedMember`?" branch.
 */
export function TeamMemberRoleDialog({
  member,
  open,
  onOpenChange,
  currentUserRole,
}: TeamMemberRoleDialogProps) {
  if (!member) return null;
  return (
    <EditMemberDialog
      open={open}
      onOpenChange={onOpenChange}
      member={member}
      currentUserRole={currentUserRole}
    />
  );
}
