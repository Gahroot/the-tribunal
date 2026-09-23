"use client";

import { X } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";

import { ContactSidebar } from "@/components/contacts/contact-sidebar";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useContact } from "@/hooks/useContacts";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { useContactStore } from "@/lib/contact-store";
import { cn } from "@/lib/utils";

interface ContactDetailPanelProps {
  contactId: number;
  /** Clears the `?contact=` param without scrolling or remounting the list. */
  onClose: () => void;
  className?: string;
}

/**
 * Master-detail detail column for `/contacts`.
 *
 * Selection lives in the `?contact=<id>` URL param, so the list column never
 * unmounts: scroll position, filters, and sort survive every selection. The
 * panel adopts the fetched contact into the shared store (the same contract
 * `/contacts/[id]` uses), so switching contacts re-renders the sidebar in
 * place instead of remounting a route.
 */
export function ContactDetailPanel({ contactId, onClose, className }: ContactDetailPanelProps) {
  const workspaceId = useWorkspaceId();
  const { selectedContact, setSelectedContact } = useContactStore();
  const { data: contact, isPending, isError } = useContact(workspaceId ?? "", contactId);

  const isShowingRequestedContact = selectedContact?.id === contactId;

  // Deep link / back-forward: adopt the fetched contact into the store so the
  // sidebar reflows in place for this id. Card clicks set the store first for
  // an instant paint; this effect covers cold loads and history navigation.
  useEffect(() => {
    if (contact && selectedContact?.id !== contact.id) {
      setSelectedContact(contact);
    }
  }, [contact, selectedContact, setSelectedContact]);

  return (
    <aside
      aria-label="Contact details"
      className={cn("flex flex-col overflow-hidden border-l bg-background", className)}
    >
      <div className="flex shrink-0 items-center justify-between gap-2 border-b px-4 py-2.5">
        <p className="text-sm font-medium text-muted-foreground">Details</p>
        <div className="flex items-center gap-1">
          <Button asChild variant="ghost" size="sm" className="h-8 gap-1.5 px-2 text-xs">
            <Link href={`/contacts/${contactId}`}>Open conversation</Link>
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="Close details"
            className="h-8 w-8"
            onClick={onClose}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        {isShowingRequestedContact ? (
          <ContactSidebar />
        ) : isPending ? (
          <PanelSkeleton />
        ) : isError || !contact ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
            <p className="text-sm font-medium">Contact not found</p>
            <p className="text-sm text-muted-foreground">It may have been deleted.</p>
            <Button type="button" variant="outline" size="sm" onClick={onClose}>
              Close details
            </Button>
          </div>
        ) : (
          // Fetched — the store sync above lands on the next render.
          <PanelSkeleton />
        )}
      </div>
    </aside>
  );
}

function PanelSkeleton() {
  return (
    <div className="space-y-4 p-4" aria-hidden="true">
      <Skeleton className="h-12 w-12 rounded-full" />
      <Skeleton className="h-5 w-40" />
      <Skeleton className="h-4 w-56" />
      <Skeleton className="h-24 w-full rounded-lg" />
      <Skeleton className="h-24 w-full rounded-lg" />
    </div>
  );
}
