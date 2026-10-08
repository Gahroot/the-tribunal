"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import * as z from "zod";

import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  FormDescription,
} from "@/components/ui/form";
import { FormDialog } from "@/components/ui/form-dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { workspacesApi, type CreateWorkspaceRequest, type WorkspaceResponse } from "@/lib/api/workspaces";
import { useFormDialog } from "@/lib/forms/use-form-dialog";
import { useWorkspace } from "@/providers/workspace-provider";

const workspaceFormSchema = z.object({
  name: z.string().min(1, { error: "Name is required" }).max(200, { error: "Name must be 200 characters or less" }),
  slug: z
    .string()
    .min(1, { error: "Slug is required" })
    .max(100, { error: "Slug must be 100 characters or less" })
    .regex(/^[a-z0-9-]+$/, "Slug must contain only lowercase letters, numbers, and hyphens"),
  description: z.string().optional(),
});

type WorkspaceFormValues = z.infer<typeof workspaceFormSchema>;

const defaultValues: WorkspaceFormValues = {
  name: "",
  slug: "",
  description: "",
};

function generateSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .slice(0, 100);
}

interface CreateWorkspaceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateWorkspaceDialog({ open, onOpenChange }: CreateWorkspaceDialogProps) {
  const { activateCreatedWorkspace } = useWorkspace();
  const [createdWorkspace, setCreatedWorkspace] = useState<WorkspaceResponse | null>(null);

  // Closing abandons only the local handoff, not the committed workspace.
  if (!open && createdWorkspace) setCreatedWorkspace(null);

  const createWorkspaceMutation = useMutation({
    mutationFn: (data: CreateWorkspaceRequest) => workspacesApi.create(data),
  });

  const dialog = useFormDialog<WorkspaceFormValues>({
    open,
    onOpenChange,
    schema: workspaceFormSchema,
    defaultValues,
    errorFallback: "Failed to create workspace. Please try again.",
    // Map a known slug collision to a field error; anything else is a toast.
    onTopLevelError: (message) => {
      if (createdWorkspace) {
        toast.error(`${createdWorkspace.name} was created, but could not be activated. Retry opening setup or select it later from the workspace menu.`);
        return;
      }
      if (message.includes("slug already exists")) {
        dialog.form.setError("slug", { message: "This slug is already taken" });
        return;
      }
      toast.error("Failed to create workspace. Please try again.");
    },
    onSubmit: async (data) => {
      const workspace = createdWorkspace ?? await createWorkspaceMutation.mutateAsync({
        name: data.name,
        slug: data.slug,
        description: data.description || undefined,
      });
      setCreatedWorkspace(workspace);
      try {
        await activateCreatedWorkspace(workspace.id);
      } catch {
        // Creation committed: never invite a duplicate create or claim activation.
        toast.error(`${workspace.name} was created, but could not be activated. Retry opening setup or select it later from the workspace menu.`);
        return;
      }
      toast.success(`${workspace.name} is active. Continue setup.`);
      onOpenChange(false);
    },
  });

  const { form } = dialog;

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const name = e.target.value;
    // Auto-generate slug from name if slug is empty or was auto-generated.
    const currentSlug = form.getValues("slug");
    const previousName = form.getValues("name");
    form.setValue("name", name);
    if (!currentSlug || currentSlug === generateSlug(previousName)) {
      form.setValue("slug", generateSlug(name));
    }
  };

  return (
    <FormDialog
      dialog={dialog}
      open={open}
      title={createdWorkspace ? `Set up ${createdWorkspace.name}` : "Create Workspace"}
      description={createdWorkspace
        ? `${createdWorkspace.name} has been created. Open its setup after confirming your workspace membership.`
        : "Create a new workspace to organize your contacts, campaigns, and team."}
      submitLabel={createdWorkspace ? "Open setup" : "Create Workspace"}
      submitBusyLabel={createdWorkspace ? "Opening setup..." : "Creating..."}
      className="sm:max-w-[450px]"
    >
      <FormField
        control={form.control}
        name="name"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Name *</FormLabel>
            <FormControl>
              <Input placeholder="My Company" {...field} onChange={handleNameChange} disabled={!!createdWorkspace} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="slug"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Slug *</FormLabel>
            <FormControl>
              <Input placeholder="my-company" {...field} disabled={!!createdWorkspace} />
            </FormControl>
            <FormDescription>
              URL-friendly identifier (lowercase, numbers, hyphens only)
            </FormDescription>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="description"
        render={({ field }) => (
          <FormItem>
            <FormLabel>Description</FormLabel>
            <FormControl>
              <Textarea
                disabled={!!createdWorkspace}
                placeholder="A brief description of this workspace..."
                className="min-h-[80px]"
                {...field}
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
    </FormDialog>
  );
}
