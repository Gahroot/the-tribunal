"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import * as z from "zod";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { FormDialog } from "@/components/ui/form-dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { workspacesApi } from "@/lib/api/workspaces";
import { useFormDialog } from "@/lib/forms/use-form-dialog";
import { queryKeys } from "@/lib/query-keys";

const editMemberSchema = z.object({
  role: z.enum(["admin", "member"]),
});

type EditMemberValues = z.infer<typeof editMemberSchema>;

interface EditMemberDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  member: {
    id: number;
    email: string;
    full_name: string | null;
    role: string;
  };
  currentUserRole: string;
}

export function EditMemberDialog({
  open,
  onOpenChange,
  member,
  currentUserRole,
}: EditMemberDialogProps) {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();

  // Can only edit if current user is owner/admin and target is not owner.
  const canEditRole = member.role !== "owner" && currentUserRole !== "member";
  const canRemove =
    member.role !== "owner" &&
    (currentUserRole === "owner" ||
      (currentUserRole === "admin" && member.role !== "admin"));

  const updateRoleMutation = useMutation({
    mutationFn: (role: "admin" | "member") =>
      workspacesApi.updateMemberRole(workspaceId!, member.id, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.settings.team(workspaceId ?? "") });
      toast.success("Member role updated");
    },
  });

  const removeMemberMutation = useMutation({
    mutationFn: () => workspacesApi.removeMember(workspaceId!, member.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.settings.team(workspaceId ?? "") });
      toast.success("Member removed from workspace");
      onOpenChange(false);
    },
    onError: (error: Error) => {
      toast.error(error.message || "Failed to remove member");
    },
  });

  const dialog = useFormDialog<EditMemberValues>({
    open,
    onOpenChange,
    schema: editMemberSchema,
    // Re-syncs when the dialog adopts a different member (edit-dialog reset).
    defaultValues: { role: member.role === "admin" ? "admin" : "member" },
    errorFallback: "Failed to update member role",
    onTopLevelError: (message) => toast.error(message),
    onSubmit: async (values) => {
      if (values.role === member.role) {
        onOpenChange(false);
        return;
      }
      await updateRoleMutation.mutateAsync(values.role);
      onOpenChange(false);
    },
  });

  const { form } = dialog;

  const removeButton = canRemove ? (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          type="button"
          variant="destructive"
          className="sm:mr-auto"
          disabled={removeMemberMutation.isPending}
        >
          <Trash2 className="mr-2 h-4 w-4" />
          Remove
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Remove Team Member</AlertDialogTitle>
          <AlertDialogDescription>
            Are you sure you want to remove {member.full_name || member.email} from this
            workspace? They will lose access to all workspace resources.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={() => removeMemberMutation.mutate()}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {removeMemberMutation.isPending ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Removing...
              </>
            ) : (
              "Remove Member"
            )}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  ) : null;

  return (
    <FormDialog
      dialog={dialog}
      open={open}
      title="Edit Team Member"
      description={`Manage ${member.full_name || member.email}'s role and access.`}
      submitLabel="Save Changes"
      submitBusyLabel="Saving..."
      submitDisabled={!canEditRole}
      footerExtra={removeButton}
      className="sm:max-w-[425px]"
    >
      <div className="space-y-2">
        <Label>Email</Label>
        <p className="text-sm text-muted-foreground">{member.email}</p>
      </div>

      {member.role === "owner" ? (
        <div className="space-y-2">
          <Label>Role</Label>
          <p className="text-sm text-muted-foreground capitalize">
            {member.role} (cannot be changed)
          </p>
        </div>
      ) : (
        <FormField
          control={form.control}
          name="role"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Role</FormLabel>
              <Select
                value={field.value}
                onValueChange={field.onChange}
                disabled={!canEditRole}
              >
                <FormControl>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  <SelectItem value="member">
                    <div>
                      <div className="font-medium">Member</div>
                      <div className="text-xs text-muted-foreground">
                        Can view and manage contacts, campaigns
                      </div>
                    </div>
                  </SelectItem>
                  <SelectItem value="admin">
                    <div>
                      <div className="font-medium">Admin</div>
                      <div className="text-xs text-muted-foreground">
                        Full access including team management
                      </div>
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />
      )}
    </FormDialog>
  );
}
