"use client";

import { AlertCircle } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { VirtualContactSelector } from "../virtual-contact-selector";

interface ContactsStepProps {
  workspaceId: string;
  selectedIds: Set<number>;
  onSelectionChange: (ids: Set<number>) => void;
  error?: string;
}

export function ContactsStep({
  workspaceId,
  selectedIds,
  onSelectionChange,
  error,
}: ContactsStepProps) {
  return (
    <div className="space-y-4">
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="size-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <VirtualContactSelector
        workspaceId={workspaceId}
        selectedIds={selectedIds}
        onSelectionChange={onSelectionChange}
      />
    </div>
  );
}
