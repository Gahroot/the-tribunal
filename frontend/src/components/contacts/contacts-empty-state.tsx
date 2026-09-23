"use client";

import { Plus, Upload, User } from "lucide-react";

import { Button } from "@/components/ui/button";
import { PageEmptyState } from "@/components/ui/page-state";

export interface ContactsEmptyStateProps {
  hasFilters: boolean;
  onAddContact: () => void;
  onImportContacts: () => void;
}

export function ContactsEmptyState({
  hasFilters,
  onAddContact,
  onImportContacts,
}: ContactsEmptyStateProps) {
  if (hasFilters) {
    return (
      <PageEmptyState
        icon={<User className="size-12" />}
        title="No contacts found"
        description="Try adjusting your search or filters."
      />
    );
  }

  return (
    <PageEmptyState
      icon={<User className="size-12" />}
      title="No contacts yet"
      description="Import your list or add a contact to get started."
      action={
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button className="gap-2" onClick={onAddContact}>
            <Plus className="h-4 w-4" />
            Add contact
          </Button>
          <Button variant="outline" className="gap-2" onClick={onImportContacts}>
            <Upload className="h-4 w-4" />
            Import CSV
          </Button>
        </div>
      }
    />
  );
}
