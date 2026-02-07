"use client";

import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import * as z from "zod";
import { Loader2 } from "lucide-react";

import { contactsApi, type UpdateContactRequest } from "@/lib/api/contacts";
import { contactQueryKeys } from "@/hooks/useContacts";
import { useContactStore } from "@/lib/contact-store";
import { useWorkspaceId } from "@/hooks/use-workspace-id";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Contact, ContactStatus } from "@/types";

const contactFormSchema = z.object({
  first_name: z.string().min(1, "First name is required"),
  last_name: z.string().optional(),
  email: z.string().email("Invalid email").optional().or(z.literal("")),
  phone_number: z.string().min(10, "Phone number must be at least 10 digits"),
  company_name: z.string().optional(),
  status: z.enum(["new", "contacted", "qualified", "converted", "lost"]),
  tags: z.string().optional(),
  notes: z.string().optional(),
});

type ContactFormValues = z.infer<typeof contactFormSchema>;

interface EditContactDialogProps {
  contact: Contact;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EditContactDialog({ contact, open, onOpenChange }: EditContactDialogProps) {
  const queryClient = useQueryClient();
  const { setSelectedContact } = useContactStore();
  const workspaceId = useWorkspaceId();
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Convert tags to string for form
  const tagsString = Array.isArray(contact.tags)
    ? contact.tags.join(", ")
    : typeof contact.tags === "string"
      ? contact.tags
      : "";

  const form = useForm<ContactFormValues>({
    resolver: zodResolver(contactFormSchema),
    defaultValues: {
      first_name: contact.first_name || "",
      last_name: contact.last_name || "",
      email: contact.email || "",
      phone_number: contact.phone_number || "",
      company_name: contact.company_name || "",
      status: contact.status || "new",
      tags: tagsString,
      notes: contact.notes || "",
    },
  });

  // Reset form when contact changes
  useEffect(() => {
    const newTagsString = Array.isArray(contact.tags)
      ? contact.tags.join(", ")
      : typeof contact.tags === "string"
        ? contact.tags
        : "";

    form.reset({
      first_name: contact.first_name || "",
      last_name: contact.last_name || "",
      email: contact.email || "",
      phone_number: contact.phone_number || "",
      company_name: contact.company_name || "",
      status: contact.status || "new",
      tags: newTagsString,
      notes: contact.notes || "",
    });
  }, [contact, form]);

  const updateContactMutation = useMutation({
    mutationFn: (data: UpdateContactRequest) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return contactsApi.update(workspaceId, contact.id, data);
    },
    onSuccess: (updatedContact) => {
      // Invalidate queries to trigger refetch
      queryClient.invalidateQueries({ queryKey: contactQueryKeys.all(workspaceId ?? "") });
      queryClient.invalidateQueries({ queryKey: contactQueryKeys.get(workspaceId ?? "", contact.id) });
      setSelectedContact(updatedContact);
      toast.success("Contact updated successfully!");
      onOpenChange(false);
    },
    onError: (error) => {
      console.error("Failed to update contact:", error);
      toast.error("Failed to update contact. Please try again.");
    },
    onSettled: () => {
      setIsSubmitting(false);
    },
  });

  const handleSubmit = (data: ContactFormValues) => {
    if (isSubmitting) return;
    setIsSubmitting(true);

    // Convert comma-separated tags string to array
    const tagsArray = data.tags
      ? data.tags.split(",").map((tag) => tag.trim()).filter(Boolean)
      : undefined;

    const request: UpdateContactRequest = {
      first_name: data.first_name,
      last_name: data.last_name || undefined,
      email: data.email || undefined,
      phone_number: data.phone_number,
      company_name: data.company_name || undefined,
      status: data.status as ContactStatus,
      tags: tagsArray,
      notes: data.notes || undefined,
    };

    updateContactMutation.mutate(request);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Edit Contact</DialogTitle>
          <DialogDescription>
            Update the contact details below. Required fields are marked with *.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <FormField
                control={form.control}
                name="first_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>First Name *</FormLabel>
                    <FormControl>
                      <Input placeholder="John" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="last_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Last Name</FormLabel>
                    <FormControl>
                      <Input placeholder="Doe" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="phone_number"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Phone Number *</FormLabel>
                  <FormControl>
                    <Input placeholder="+1 (555) 123-4567" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Email</FormLabel>
                  <FormControl>
                    <Input type="email" placeholder="john@example.com" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="company_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Company</FormLabel>
                  <FormControl>
                    <Input placeholder="Acme Inc." {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="status"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Status</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select status" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="new">New</SelectItem>
                      <SelectItem value="contacted">Contacted</SelectItem>
                      <SelectItem value="qualified">Qualified</SelectItem>
                      <SelectItem value="converted">Converted</SelectItem>
                      <SelectItem value="lost">Lost</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="tags"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Tags</FormLabel>
                  <FormControl>
                    <Input placeholder="vip, priority, follow-up" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="notes"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Notes</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Additional notes about this contact..."
                      className="min-h-[80px]"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {isSubmitting ? "Saving..." : "Save Changes"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
