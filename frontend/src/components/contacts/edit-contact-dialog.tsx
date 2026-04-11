"use client";

import type { Contact } from "@/types";

import { ContactFormDialog } from "./contact-form-dialog";

interface EditContactDialogProps {
  contact: Contact;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EditContactDialog({ contact, open, onOpenChange }: EditContactDialogProps) {
  return (
    <ContactFormDialog
      mode="edit"
      contact={contact}
      open={open}
      onOpenChange={onOpenChange}
    />
  );
}
