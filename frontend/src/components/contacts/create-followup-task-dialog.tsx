"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { z } from "zod";

import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { FormDialog } from "@/components/ui/form-dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { nudgesApi } from "@/lib/api/nudges";
import { settingsApi } from "@/lib/api/settings";
import { useFormDialog } from "@/lib/forms/use-form-dialog";
import { messages } from "@/lib/messages";
import { queryKeys } from "@/lib/query-keys";
import { STATIC } from "@/lib/query-options";

const followupTaskSchema = z.object({
  title: z.string().trim().min(1, { error: "Add a task title" }),
  due_date: z.string().min(1, { error: "Pick a due date" }),
  assigned_to: z.string(),
  message: z.string(),
});

type FollowupTaskFormValues = z.infer<typeof followupTaskSchema>;

/** Local calendar day as `yyyy-MM-dd`, the format `<input type="date">` expects. */
function todayISODate(): string {
  const now = new Date();
  const month = `${now.getMonth() + 1}`.padStart(2, "0");
  const day = `${now.getDate()}`.padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

export interface CreateFollowupTaskDialogProps {
  workspaceId: string;
  contactId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Follow-up task creation for the contact detail panel.
 *
 * Missive-style inline add: a successful create clears the quick-entry fields
 * and keeps the dialog open so several tasks can be entered without
 * reopening it. The chosen due date + assignee persist between adds;
 * Close/Escape resets everything via the form dialog's reset-on-close.
 */
export function CreateFollowupTaskDialog({
  workspaceId,
  contactId,
  open,
  onOpenChange,
}: CreateFollowupTaskDialogProps) {
  const queryClient = useQueryClient();

  const { data: team } = useQuery({
    queryKey: queryKeys.settings.team(workspaceId),
    queryFn: () => settingsApi.getTeamMembers(workspaceId),
    enabled: !!workspaceId,
    ...STATIC,
  });

  const dialog = useFormDialog<FollowupTaskFormValues>({
    open,
    onOpenChange,
    schema: followupTaskSchema,
    // Recomputed every render so each open defaults to today. The serialized
    // defaults key stays stable within a day, so typing never trips the
    // reset-to-new-defaults effect while the dialog is open.
    defaultValues: {
      title: "",
      message: "",
      due_date: todayISODate(),
      assigned_to: "none",
    },
    errorFallback: messages.nudges.taskCreateFailed,
    serverErrorFields: ["title", "due_date"],
    onTopLevelError: (error) => toast.error(error),
    onSubmit: async (values, form) => {
      await nudgesApi.create(workspaceId, {
        contact_id: contactId,
        title: values.title,
        message: values.message,
        // Noon local time so "Today" stays "Today" all day long.
        due_date: new Date(`${values.due_date}T12:00:00`).toISOString(),
        nudge_type: "follow_up",
        assigned_to_user_id: values.assigned_to === "none" ? null : Number(values.assigned_to),
      });

      void queryClient.invalidateQueries({
        queryKey: queryKeys.nudges.all(workspaceId),
      });
      toast.success(messages.nudges.taskCreated);

      // Stay open for rapid entry: clear the quick-entry fields, keep the
      // chosen date + assignee, and put the cursor back on the title.
      form.reset({ ...values, title: "", message: "" });
      form.setFocus("title");
    },
  });

  return (
    <FormDialog
      dialog={dialog}
      open={open}
      title="New follow-up task"
      description="Add follow-up tasks for this contact. The dialog stays open so you can add several in a row."
      submitLabel="Add task"
      submitBusyLabel="Adding..."
      cancelLabel="Close"
      className="sm:max-w-md"
    >
      <FormField
        control={dialog.form.control}
        name="title"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Title</FormLabel>
            <FormControl>
              <Input placeholder="Send pricing recap" autoComplete="off" {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          control={dialog.form.control}
          name="due_date"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Due date</FormLabel>
              <FormControl>
                <Input type="date" min={todayISODate()} {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={dialog.form.control}
          name="assigned_to"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Assign to</FormLabel>
              <Select onValueChange={field.onChange} value={field.value}>
                <FormControl>
                  <SelectTrigger className="w-full" aria-label="Assign to">
                    <SelectValue placeholder="Anyone" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  <SelectItem value="none">Anyone</SelectItem>
                  {(team ?? []).map((member) => (
                    <SelectItem key={member.id} value={String(member.id)}>
                      {member.full_name || member.email}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>

      <FormField
        control={dialog.form.control}
        name="message"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Notes</FormLabel>
            <FormControl>
              <Textarea rows={3} placeholder="Optional context for this follow-up" {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
    </FormDialog>
  );
}
