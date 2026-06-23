"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import * as z from "zod";

import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { FormDialog } from "@/components/ui/form-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { messageTemplatesApi } from "@/lib/api/message-templates";
import { useFormDialog } from "@/lib/forms/use-form-dialog";
import { queryKeys } from "@/lib/query-keys";

const saveTemplateSchema = z.object({
  name: z.string().trim().min(1, { error: "Please enter a template name" }),
});

type SaveTemplateValues = z.infer<typeof saveTemplateSchema>;

interface SaveTemplateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  messageTemplate: string;
  defaultName?: string;
}

export function SaveTemplateDialog({
  open,
  onOpenChange,
  messageTemplate,
  defaultName = "",
}: SaveTemplateDialogProps) {
  const workspaceId = useWorkspaceId();
  const queryClient = useQueryClient();

  const saveMutation = useMutation({
    mutationFn: (name: string) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return messageTemplatesApi.create(workspaceId, {
        name,
        message_template: messageTemplate,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.messageTemplates.all(workspaceId ?? ""),
      });
      toast.success("Template saved successfully");
    },
  });

  const dialog = useFormDialog<SaveTemplateValues>({
    open,
    onOpenChange,
    schema: saveTemplateSchema,
    // Seed (and re-sync) from `defaultName` so reopening on a new variation
    // shows the suggested name rather than a stale one.
    defaultValues: { name: defaultName },
    errorFallback: "Failed to save template",
    onTopLevelError: (message) => toast.error(message),
    onSubmit: async (values) => {
      await saveMutation.mutateAsync(values.name.trim());
      onOpenChange(false);
    },
  });

  const { form } = dialog;

  return (
    <FormDialog
      dialog={dialog}
      open={open}
      title="Save as Template"
      description="Save this message variation for reuse in future experiments."
      submitLabel="Save Template"
      submitBusyLabel="Saving..."
      className="sm:max-w-[450px]"
    >
      <FormField
        control={form.control}
        name="name"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Template Name</FormLabel>
            <FormControl>
              <Input
                placeholder="e.g., Friendly Introduction"
                // The dialog opens specifically so the user can type a name;
                // focusing the field on open matches the dialog focus-trap pattern.
                // eslint-disable-next-line jsx-a11y/no-autofocus
                autoFocus
                {...field}
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <div className="space-y-2">
        <Label>Message Preview</Label>
        <div className="p-3 bg-muted rounded-md text-sm whitespace-pre-wrap max-h-32 overflow-y-auto">
          {messageTemplate || "No message content"}
        </div>
      </div>
    </FormDialog>
  );
}
