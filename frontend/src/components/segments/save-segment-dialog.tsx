"use client";

import { Loader2, Save, Users } from "lucide-react";
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
import { Textarea } from "@/components/ui/textarea";
import { useCreateSegment, useSegmentPreview } from "@/hooks/useSegments";
import { useFormDialog } from "@/lib/forms/use-form-dialog";
import { formatNumber } from "@/lib/utils/number";
import type { FilterDefinition } from "@/types";

const saveSegmentSchema = z.object({
  name: z.string().trim().min(1, { error: "Name is required" }),
  description: z.string().optional(),
});

type SaveSegmentValues = z.infer<typeof saveSegmentSchema>;

const defaultValues: SaveSegmentValues = { name: "", description: "" };

interface SaveSegmentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  filters: FilterDefinition;
  workspaceId: string;
}

export function SaveSegmentDialog({
  open,
  onOpenChange,
  filters,
  workspaceId,
}: SaveSegmentDialogProps) {
  const createSegment = useCreateSegment(workspaceId);
  const { data: preview, isFetching: isPreviewFetching } = useSegmentPreview(
    workspaceId,
    open ? filters : null,
  );

  const dialog = useFormDialog<SaveSegmentValues>({
    open,
    onOpenChange,
    schema: saveSegmentSchema,
    defaultValues,
    errorFallback: "Failed to save segment",
    onTopLevelError: (message) => toast.error(message),
    onSubmit: async (values) => {
      await createSegment.mutateAsync({
        name: values.name.trim(),
        description: values.description?.trim() || undefined,
        definition: filters,
      });
      toast.success("Segment saved");
      onOpenChange(false);
    },
  });

  const { form } = dialog;

  return (
    <FormDialog
      dialog={dialog}
      open={open}
      title={
        <span className="flex items-center gap-2">
          <Save className="h-5 w-5" />
          Save as Segment
        </span>
      }
      description="Save these filter rules as a reusable segment."
      submitLabel="Save Segment"
      submitBusyLabel="Saving..."
      className="sm:max-w-md"
    >
      <FormField
        control={form.control}
        name="name"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Name</FormLabel>
            <FormControl>
              <Input placeholder="e.g., High-value leads" {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="description"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Description (optional)</FormLabel>
            <FormControl>
              <Textarea placeholder="Describe this segment..." rows={2} {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <div className="text-sm text-muted-foreground bg-muted/50 rounded-lg p-3">
        <p className="font-medium mb-1">Filter rules ({filters.rules.length})</p>
        <p>
          Logic: {filters.logic === "or" ? "Match any" : "Match all"} rule
          {filters.rules.length !== 1 ? "s" : ""}
        </p>
        <p className="mt-2 flex items-center gap-2 text-foreground">
          {isPreviewFetching ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Users className="h-3.5 w-3.5" />
          )}
          <span>
            {preview
              ? `~${formatNumber(preview.total)} contact${
                  preview.total === 1 ? "" : "s"
                } match`
              : "Counting matches…"}
          </span>
        </p>
      </div>
    </FormDialog>
  );
}
