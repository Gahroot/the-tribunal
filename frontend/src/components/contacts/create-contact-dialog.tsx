"use client";

import { ContactFormDialog } from "./contact-form-dialog";

interface CreateContactDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateContactDialog({ open, onOpenChange }: CreateContactDialogProps) {
  return <ContactFormDialog mode="create" open={open} onOpenChange={onOpenChange} />;
}
