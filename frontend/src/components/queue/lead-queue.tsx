"use client";

import { ArrowLeft, ChevronDown, ChevronUp, Search, Users, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useContactsPaginated } from "@/hooks/useContacts";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import type { ContactsListParams } from "@/lib/api/contacts";
import { useContactStore } from "@/lib/contact-store";
import { contactStatusDotColors, contactStatusLabels } from "@/lib/status-colors";
import { cn } from "@/lib/utils";
import { formatRelative } from "@/lib/utils/date";
import { getContactInitials } from "@/lib/utils/initials";
import type { Contact, ContactStatus } from "@/types";

interface LeadQueueProps {
  className?: string;
  /** Called after navigating to a contact (used to close the mobile sheet). */
  onNavigate?: () => void;
}

interface QueueRowProps {
  contact: Contact;
  isActive: boolean;
  onSelect: () => void;
}

function QueueRow({ contact, isActive, onSelect }: QueueRowProps) {
  const displayName =
    [contact.first_name, contact.last_name].filter(Boolean).join(" ") ||
    "Unknown";
  const hasUnread = (contact.unread_count ?? 0) > 0;

  return (
    <button
      type="button"
      data-active={isActive}
      onClick={onSelect}
      className={cn(
        "flex w-full items-start gap-3 rounded-lg border p-3 text-left transition-colors",
        "hover:bg-muted hover:border-accent",
        isActive
          ? "border-primary bg-secondary"
          : "border-transparent bg-card",
        hasUnread && !isActive && "border-l-2 border-l-info",
      )}
    >
      <div className="relative shrink-0">
        <Avatar className="h-9 w-9">
          <AvatarImage src={contact.avatar_url} alt={displayName} size={72} />
          <AvatarFallback className="bg-primary/10 text-primary text-xs font-medium">
            {getContactInitials(contact)}
          </AvatarFallback>
        </Avatar>
        <span
          className={cn(
            "absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-background",
            contactStatusDotColors[contact.status],
          )}
          aria-hidden
        />
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span
            className={cn(
              "truncate text-sm font-medium",
              hasUnread && "text-info",
            )}
          >
            {displayName}
          </span>
          {contact.last_message_at && (
            <span className="shrink-0 text-[10px] text-muted-foreground">
              {formatRelative(contact.last_message_at)}
            </span>
          )}
        </div>
        <div className="mt-0.5 flex items-center justify-between gap-2">
          <span className="truncate text-xs text-muted-foreground">
            {contact.company_name || contactStatusLabels[contact.status]}
          </span>
          {hasUnread && (
            <Badge
              variant="secondary"
              className="h-4 shrink-0 px-1.5 text-[10px]"
            >
              {contact.unread_count}
            </Badge>
          )}
        </div>
      </div>
    </button>
  );
}

export function LeadQueue({ className, onNavigate }: LeadQueueProps) {
  const router = useRouter();
  const workspaceId = useWorkspaceId();

  const {
    selectedContact,
    searchQuery,
    setSearchQuery,
    statusFilter,
    sortBy,
    filters,
    contactsPage,
    contactsPageSize,
    setContactsPage,
  } = useContactStore();

  // Local input mirrors the shared store so the queue reflects (and updates)
  // the same filters the operator set on the contacts page.
  const [inputValue, setInputValue] = useState(searchQuery);

  useEffect(() => {
    const timer = setTimeout(() => setSearchQuery(inputValue), 400);
    return () => clearTimeout(timer);
  }, [inputValue, setSearchQuery]);

  const listParams = useMemo<ContactsListParams>(
    () => ({
      page: contactsPage,
      page_size: contactsPageSize,
      sort_by: sortBy,
      ...(searchQuery.trim() && { search: searchQuery.trim() }),
      ...(statusFilter && { status: statusFilter as ContactStatus }),
      ...(filters && { filters: JSON.stringify(filters) }),
    }),
    [contactsPage, contactsPageSize, sortBy, searchQuery, statusFilter, filters],
  );

  const { data, isPending } = useContactsPaginated(
    workspaceId ?? "",
    listParams,
  );
  const contacts = useMemo(() => data?.items ?? [], [data?.items]);
  const total = data?.total ?? 0;
  const totalPages = data?.pages ?? 1;

  const activeIndex = useMemo(
    () => contacts.findIndex((c) => c.id === selectedContact?.id),
    [contacts, selectedContact?.id],
  );

  const goToContact = useCallback(
    (contact: Contact) => {
      router.push(`/contacts/${contact.id}`);
      onNavigate?.();
    },
    [router, onNavigate],
  );

  const goRelative = useCallback(
    (delta: number) => {
      if (contacts.length === 0) return;
      const base = activeIndex === -1 ? 0 : activeIndex + delta;
      const next = contacts[base];
      if (next) goToContact(next);
    },
    [contacts, activeIndex, goToContact],
  );

  const hasPrev = activeIndex > 0;
  const hasNext = activeIndex !== -1 && activeIndex < contacts.length - 1;

  // j/k keyboard navigation between adjacent contacts in the queue. Ignored
  // while typing into an input/textarea/contenteditable.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      if (e.key === "j") {
        e.preventDefault();
        goRelative(1);
      } else if (e.key === "k") {
        e.preventDefault();
        goRelative(-1);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [goRelative]);

  // Keep the active row scrolled into view as the operator moves through.
  const activeRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest" });
  }, [selectedContact?.id]);

  return (
    <div className={cn("flex flex-col h-full bg-background", className)}>
      {/* Header */}
      <div className="flex items-center justify-between gap-2 border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Button
            asChild
            size="icon"
            variant="ghost"
            className="h-8 w-8"
            aria-label="Back to contacts"
          >
            <Link href="/contacts">
              <ArrowLeft className="h-4 w-4" />
            </Link>
          </Button>
          <Users className="h-4 w-4 text-primary" />
          <h2 className="font-semibold">Lead Queue</h2>
          <Badge variant="secondary" className="text-xs">
            {total}
          </Badge>
        </div>
        <div className="flex items-center gap-0.5">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8"
                onClick={() => goRelative(-1)}
                disabled={!hasPrev}
                aria-label="Previous lead"
              >
                <ChevronUp className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Previous (k)</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8"
                onClick={() => goRelative(1)}
                disabled={!hasNext}
                aria-label="Next lead"
              >
                <ChevronDown className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Next (j)</TooltipContent>
          </Tooltip>
        </div>
      </div>

      {/* Search */}
      <div className="border-b p-3">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Search leads..."
            className="h-8 pl-8 pr-8"
          />
          {inputValue && (
            <button
              type="button"
              onClick={() => setInputValue("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              aria-label="Clear search"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* List */}
      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-1 p-2">
          {isPending ? (
            <div className="space-y-1">
              {Array.from({ length: 8 }).map((_, i) => (
                <div
                  key={i}
                  className="flex items-center gap-3 rounded-lg p-3"
                >
                  <div className="h-9 w-9 animate-pulse rounded-full bg-muted" />
                  <div className="flex-1 space-y-2">
                    <div className="h-3 w-24 animate-pulse rounded bg-muted" />
                    <div className="h-2.5 w-16 animate-pulse rounded bg-muted" />
                  </div>
                </div>
              ))}
            </div>
          ) : contacts.length === 0 ? (
            <div className="px-3 py-10 text-center text-sm text-muted-foreground">
              {searchQuery.trim() || statusFilter || filters
                ? "No leads match the current filters."
                : "No leads yet."}
            </div>
          ) : (
            contacts.map((contact) => {
              const isActive = contact.id === selectedContact?.id;
              return (
                <div key={contact.id} ref={isActive ? activeRef : undefined}>
                  <QueueRow
                    contact={contact}
                    isActive={isActive}
                    onSelect={() => goToContact(contact)}
                  />
                </div>
              );
            })
          )}
        </div>
      </ScrollArea>

      {/* Pagination footer */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between gap-2 border-t px-3 py-2">
          <Button
            size="sm"
            variant="ghost"
            className="h-8"
            onClick={() => setContactsPage(Math.max(1, contactsPage - 1))}
            disabled={contactsPage <= 1}
          >
            <ChevronUp className="mr-1 h-3.5 w-3.5" />
            Prev
          </Button>
          <span className="text-xs text-muted-foreground">
            Page {contactsPage} of {totalPages}
          </span>
          <Button
            size="sm"
            variant="ghost"
            className="h-8"
            onClick={() =>
              setContactsPage(Math.min(totalPages, contactsPage + 1))
            }
            disabled={contactsPage >= totalPages}
          >
            Next
            <ChevronDown className="ml-1 h-3.5 w-3.5" />
          </Button>
        </div>
      )}
    </div>
  );
}
