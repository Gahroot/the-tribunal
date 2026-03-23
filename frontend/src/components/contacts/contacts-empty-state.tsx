"use client";

import { User, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface ContactsEmptyStateProps {
  hasFilters: boolean;
  onAddContact: () => void;
}

export function ContactsEmptyState({ hasFilters, onAddContact }: ContactsEmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <User className="h-16 w-16 text-muted-foreground/50 mb-4" />
      <h3 className="text-lg font-medium mb-1">
        {hasFilters ? "No contacts found" : "No contacts yet"}
      </h3>
      <p className="text-sm text-muted-foreground mb-4">
        {hasFilters
          ? "Try adjusting your search or filters"
          : "Get started by adding your first contact"}
      </p>
      {!hasFilters && (
        <Button className="gap-2" onClick={onAddContact}>
          <Plus className="h-4 w-4" />
          Add Contact
        </Button>
      )}
    </div>
  );
}
