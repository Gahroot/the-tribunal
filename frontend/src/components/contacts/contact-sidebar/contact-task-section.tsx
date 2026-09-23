import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Calendar as CalendarIcon, Plus } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { CreateFollowupTaskDialog } from "@/components/contacts/create-followup-task-dialog";
import { PRIORITY_STYLES, formatDueDate } from "@/components/nudges/nudge-presentation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar-lazy";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { type UpdateNudgeRequest, nudgesApi } from "@/lib/api/nudges";
import { settingsApi } from "@/lib/api/settings";
import { messages } from "@/lib/messages";
import { queryKeys } from "@/lib/query-keys";
import { STATIC } from "@/lib/query-options";
import { cn } from "@/lib/utils";
import { getApiErrorMessage } from "@/lib/utils/errors";

interface ContactTaskSectionProps {
  workspaceId: string;
  contactId: number;
}

/**
 * "Next task" for the contact detail panel: the earliest open follow-up plus
 * inline editing of its due date and assignee (Missive-style edit-in-place),
 * and the stay-open create dialog for adding follow-ups without leaving the
 * contact.
 */
export function ContactTaskSection({ workspaceId, contactId }: ContactTaskSectionProps) {
  const headingId = useId();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [dueOpen, setDueOpen] = useState(false);

  // Default status filter (pending + sent) ordered by due date, so the first
  // item is the next open task.
  const listParams = { contact_id: contactId, page: 1, page_size: 20 };
  const { data, isPending } = useQuery({
    queryKey: queryKeys.nudges.list(workspaceId, listParams),
    queryFn: () => nudgesApi.list(workspaceId, listParams),
    enabled: !!workspaceId && contactId > 0,
  });

  const { data: team } = useQuery({
    queryKey: queryKeys.settings.team(workspaceId),
    queryFn: () => settingsApi.getTeamMembers(workspaceId),
    enabled: !!workspaceId,
    ...STATIC,
  });

  const nextTask = data?.items[0];
  const remainingCount = data ? Math.max(data.total - data.items.length, 0) : 0;

  const updateMutation = useMutation({
    mutationFn: (variables: { id: string; data: UpdateNudgeRequest }) =>
      nudgesApi.update(workspaceId, variables.id, variables.data),
    onSuccess: (_result, variables) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.nudges.all(workspaceId),
      });
      toast.success(
        variables.data.due_date !== undefined
          ? messages.nudges.taskDueUpdated
          : messages.nudges.taskAssigned,
      );
    },
    onError: (error, variables) => {
      toast.error(
        getApiErrorMessage(
          error,
          variables.data.due_date !== undefined
            ? messages.nudges.taskDueUpdateFailed
            : messages.nudges.taskAssignFailed,
        ),
      );
    },
  });

  const handleDueDateSelect = (day: Date | undefined) => {
    if (!day || !nextTask) return;
    // Noon local time so "Today" stays "Today" for the rest of the day.
    const noon = new Date(day);
    noon.setHours(12, 0, 0, 0);
    updateMutation.mutate({
      id: nextTask.id,
      data: { due_date: noon.toISOString() },
    });
    setDueOpen(false);
  };

  const handleAssign = (value: string) => {
    if (!nextTask) return;
    updateMutation.mutate({
      id: nextTask.id,
      data: { assigned_to_user_id: value === "none" ? null : Number(value) },
    });
  };

  return (
    <section aria-labelledby={headingId} className="space-y-2">
      <div className="flex items-center justify-between gap-2 px-2">
        <h3 id={headingId} className="text-sm font-medium text-muted-foreground">
          Next task
        </h3>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-7 gap-1 px-2 text-xs"
          onClick={() => setCreateOpen(true)}
        >
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          New task
        </Button>
      </div>

      {isPending ? (
        <Skeleton className="mx-2 h-16 rounded-lg" />
      ) : nextTask ? (
        <div className="mx-2 space-y-2 rounded-lg border p-3">
          <div className="flex items-start justify-between gap-2">
            <p className="min-w-0 break-words text-sm font-medium">{nextTask.title}</p>
            <Badge
              className={cn("shrink-0 text-xs capitalize", PRIORITY_STYLES[nextTask.priority])}
            >
              {nextTask.priority}
            </Badge>
          </div>
          {nextTask.message ? (
            <p className="line-clamp-2 text-xs text-muted-foreground">{nextTask.message}</p>
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            <Popover open={dueOpen} onOpenChange={setDueOpen}>
              <PopoverTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-7 gap-1.5 px-2 text-xs text-muted-foreground"
                  aria-label="Edit due date"
                  disabled={updateMutation.isPending}
                >
                  <CalendarIcon className="h-3.5 w-3.5" aria-hidden="true" />
                  {formatDueDate(nextTask.due_date)}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0" align="start">
                <Calendar
                  mode="single"
                  selected={new Date(nextTask.due_date)}
                  onSelect={handleDueDateSelect}
                  disabled={(day) => {
                    const startOfToday = new Date();
                    startOfToday.setHours(0, 0, 0, 0);
                    return day < startOfToday;
                  }}
                  initialFocus
                />
              </PopoverContent>
            </Popover>

            <Select
              value={
                nextTask.assigned_to_user_id != null ? String(nextTask.assigned_to_user_id) : "none"
              }
              onValueChange={handleAssign}
              disabled={updateMutation.isPending}
            >
              <SelectTrigger size="sm" className="h-7 w-[150px] text-xs" aria-label="Task assignee">
                <SelectValue placeholder="Anyone" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Anyone</SelectItem>
                {(team ?? []).map((member) => (
                  <SelectItem key={member.id} value={String(member.id)}>
                    {member.full_name || member.email}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {remainingCount > 0 ? (
            <p className="text-xs text-muted-foreground">
              +{remainingCount} more open {remainingCount === 1 ? "task" : "tasks"}
            </p>
          ) : null}
        </div>
      ) : (
        <p className="px-2 text-sm text-muted-foreground">No open tasks.</p>
      )}

      <CreateFollowupTaskDialog
        workspaceId={workspaceId}
        contactId={contactId}
        open={createOpen}
        onOpenChange={setCreateOpen}
      />
    </section>
  );
}
