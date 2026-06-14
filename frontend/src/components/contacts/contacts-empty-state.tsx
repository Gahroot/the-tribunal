"use client";

import { Plus, Upload, User } from "lucide-react";

import { Button } from "@/components/ui/button";

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
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <User className="h-16 w-16 text-muted-foreground/50 mb-4" />
      <h3 className="text-lg font-medium mb-1">
        {hasFilters ? "No contacts found" : "No contacts yet"}
      </h3>
      <p className="text-sm text-muted-foreground mb-4">
        {hasFilters
          ? "Try adjusting your search or filters"
          : "Get started by importing your list or adding a contact"}
      </p>
      {!hasFilters && (
        <div className="flex flex-col gap-2 sm:flex-row">
          <Button className="gap-2" onClick={onAddContact}>
            <Plus className="h-4 w-4" />
            Add Contact
          </Button>
          <Button variant="outline" className="gap-2" onClick={onImportContacts}>
            <Upload className="h-4 w-4" />
            Import CSV
          </Button>
        </div>
      )}
    </div>
  );
}
