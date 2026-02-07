"use client";

import * as React from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { Search, Plus, User, Phone, Mail, Users, Upload, Trash2, X, CheckSquare, MapPin, ArrowUpDown, Tags } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";
import { useContactStore } from "@/lib/contact-store";
import { CreateContactDialog } from "@/components/contacts/create-contact-dialog";
import { ImportContactsDialog } from "@/components/contacts/import-contacts-dialog";
import { ScrapeLeadsDialog } from "@/components/contacts/scrape-leads-dialog";
import { BulkTagDialog } from "@/components/contacts/bulk-tag-dialog";
import { TagBadge } from "@/components/tags/tag-badge";
import { ContactFilterBuilder } from "@/components/filters/contact-filter-builder";
import { useBulkDeleteContacts } from "@/hooks/useContacts";
import { useWorkspaceId } from "@/hooks/use-workspace-id";
import { contactStatusColors, contactStatusLabels } from "@/lib/status-colors";
import type { Contact, ContactStatus } from "@/types";
import type { ContactSortBy } from "@/lib/api/contacts";

function getInitials(contact: Contact): string {
  const first = contact.first_name?.[0] ?? "";
  const last = contact.last_name?.[0] ?? "";
  return (first + last).toUpperCase() || "?";
}

function formatPhoneNumber(phone?: string): string {
  if (!phone) return "";
  const cleaned = phone.replace(/\D/g, "");
  if (cleaned.length === 10) {
    return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
  }
  if (cleaned.length === 11 && cleaned[0] === "1") {
    return `+1 (${cleaned.slice(1, 4)}) ${cleaned.slice(4, 7)}-${cleaned.slice(7)}`;
  }
  return phone;
}

function ContactCardSkeleton() {
  return (
    <div className="flex flex-col p-4 rounded-xl border bg-card">
      <div className="flex items-start gap-3">
        <Skeleton className="h-12 w-12 rounded-full" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-4 w-24" />
        </div>
      </div>
      <div className="mt-3 space-y-2">
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-3/4" />
      </div>
    </div>
  );
}

interface ContactCardProps {
  contact: Contact;
  isSelected: boolean;
  onSelectChange: (checked: boolean) => void;
  isSelectionMode: boolean;
}

function ContactCard({ contact, isSelected, onSelectChange, isSelectionMode }: ContactCardProps) {
  const displayName = [contact.first_name, contact.last_name].filter(Boolean).join(" ") || "Unknown";
  const hasUnread = (contact.unread_count ?? 0) > 0;

  const handleCheckboxClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onSelectChange(!isSelected);
  };

  const cardContent = (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.2 }}
      className={cn(
        "flex flex-col p-4 rounded-xl border bg-card",
        "hover:bg-accent/50 hover:border-accent transition-all cursor-pointer",
        "group",
        isSelected && "ring-2 ring-primary border-primary",
        hasUnread && "border-l-4 border-l-blue-500"
      )}
    >
      <div className="flex items-start gap-3">
        {isSelectionMode && (
          <div className="shrink-0 pt-1" onClick={handleCheckboxClick}>
            <Checkbox
              checked={isSelected}
              onCheckedChange={(checked) => onSelectChange(checked === true)}
            />
          </div>
        )}
        <div className="relative">
          <Avatar className="h-12 w-12 shrink-0">
            <AvatarFallback className="bg-primary/10 text-primary text-base font-medium">
              {getInitials(contact)}
            </AvatarFallback>
          </Avatar>
          {hasUnread && (
            <span className="absolute -top-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-blue-500 text-[10px] font-bold text-white">
              {contact.unread_count}
            </span>
          )}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <span className={cn(
              "font-semibold truncate group-hover:text-primary transition-colors",
              hasUnread && "text-blue-600 dark:text-blue-400"
            )}>
              {displayName}
            </span>
            <Badge variant="secondary" className={cn("text-xs shrink-0", contactStatusColors[contact.status])}>
              {contactStatusLabels[contact.status]}
            </Badge>
          </div>
          {contact.company_name && (
            <p className="text-sm text-muted-foreground truncate mt-0.5">
              {contact.company_name}
            </p>
          )}
        </div>
      </div>

      <div className="mt-3 flex flex-col gap-1.5 text-sm text-muted-foreground">
        {contact.phone_number && (
          <div className="flex items-center gap-2 truncate">
            <Phone className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{formatPhoneNumber(contact.phone_number)}</span>
          </div>
        )}
        {contact.email && (
          <div className="flex items-center gap-2 truncate">
            <Mail className="h-3.5 w-3.5 shrink-0" />
            <span className="truncate">{contact.email}</span>
          </div>
        )}
      </div>

      {(() => {
        // Prefer tag_objects (colored) from new system, fall back to legacy string tags
        if (contact.tag_objects && contact.tag_objects.length > 0) {
          return (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {contact.tag_objects.slice(0, 3).map((tag) => (
                <TagBadge key={tag.id} name={tag.name} color={tag.color} />
              ))}
              {contact.tag_objects.length > 3 && (
                <Badge variant="outline" className="text-xs">
                  +{contact.tag_objects.length - 3}
                </Badge>
              )}
            </div>
          );
        }
        if (contact.tags) {
          const tagsArray = Array.isArray(contact.tags)
            ? contact.tags
            : typeof contact.tags === "string"
              ? contact.tags.split(",").map((t) => t.trim()).filter(Boolean)
              : [];
          if (tagsArray.length > 0) {
            return (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {tagsArray.slice(0, 3).map((tag) => (
                  <Badge key={tag} variant="outline" className="text-xs">
                    {tag}
                  </Badge>
                ))}
                {tagsArray.length > 3 && (
                  <Badge variant="outline" className="text-xs">
                    +{tagsArray.length - 3}
                  </Badge>
                )}
              </div>
            );
          }
        }
        return null;
      })()}
    </motion.div>
  );

  if (isSelectionMode) {
    return (
      <div onClick={() => onSelectChange(!isSelected)}>
        {cardContent}
      </div>
    );
  }

  return <Link href={`/contacts/${contact.id}`}>{cardContent}</Link>;
}

interface StatusFilterProps {
  selectedStatus: ContactStatus | null;
  onStatusChange: (status: ContactStatus | null) => void;
  counts: Record<ContactStatus | "all", number>;
}

function StatusFilter({ selectedStatus, onStatusChange, counts }: StatusFilterProps) {
  const statuses: (ContactStatus | "all")[] = ["all", "new", "contacted", "qualified", "converted", "lost"];

  return (
    <div className="flex flex-wrap gap-2">
      {statuses.map((status) => (
        <Button
          key={status}
          variant={selectedStatus === status || (status === "all" && !selectedStatus) ? "default" : "outline"}
          size="sm"
          onClick={() => onStatusChange(status === "all" ? null : status)}
          className={cn(
            "gap-1.5",
            status !== "all" && selectedStatus !== status && contactStatusColors[status]
          )}
        >
          {status === "all" ? "All" : contactStatusLabels[status]}
          <span className="text-xs opacity-70">({counts[status]})</span>
        </Button>
      ))}
    </div>
  );
}

export function ContactsPage() {
  const [isCreateDialogOpen, setIsCreateDialogOpen] = React.useState(false);
  const [isImportDialogOpen, setIsImportDialogOpen] = React.useState(false);
  const [isScrapeDialogOpen, setIsScrapeDialogOpen] = React.useState(false);
  const [selectedIds, setSelectedIds] = React.useState<number[]>([]);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = React.useState(false);
  const [isBulkTagDialogOpen, setIsBulkTagDialogOpen] = React.useState(false);
  const workspaceId = useWorkspaceId();
  const bulkDeleteMutation = useBulkDeleteContacts(workspaceId ?? "");
  const {
    contacts,
    searchQuery,
    setSearchQuery,
    statusFilter,
    setStatusFilter,
    sortBy,
    setSortBy,
    isLoadingContacts,
    setContacts,
    filters,
    setFilters,
  } = useContactStore();

  const isSelectionMode = selectedIds.length > 0;

  const handleSelectContact = (contactId: number, checked: boolean) => {
    setSelectedIds((prev) =>
      checked ? [...prev, contactId] : prev.filter((id) => id !== contactId)
    );
  };

  const handleSelectAll = () => {
    if (selectedIds.length === filteredContacts.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(filteredContacts.map((c) => c.id));
    }
  };

  const handleClearSelection = () => {
    setSelectedIds([]);
  };

  const handleBulkDelete = async () => {
    if (!workspaceId || selectedIds.length === 0) return;

    try {
      await bulkDeleteMutation.mutateAsync(selectedIds);
      setContacts(contacts.filter((c) => !selectedIds.includes(c.id)));
      setSelectedIds([]);
      setIsDeleteDialogOpen(false);
    } catch (error) {
      console.error("Failed to delete contacts:", error);
    }
  };

  // Calculate status counts
  const statusCounts = React.useMemo(() => {
    const counts: Record<ContactStatus | "all", number> = {
      all: contacts.length,
      new: 0,
      contacted: 0,
      qualified: 0,
      converted: 0,
      lost: 0,
    };
    contacts.forEach((contact) => {
      counts[contact.status]++;
    });
    return counts;
  }, [contacts]);

  // Filter contacts based on search query and status filter
  // eslint-disable-next-line react-hooks/preserve-manual-memoization
  const filteredContacts = React.useMemo(() => {
    let filtered = contacts;

    // Apply status filter
    if (statusFilter) {
      filtered = filtered.filter((contact) => contact.status === statusFilter);
    }

    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter((contact) => {
        const fullName = `${contact.first_name} ${contact.last_name}`.toLowerCase();
        const phone = contact.phone_number?.toLowerCase() ?? "";
        const email = contact.email?.toLowerCase() ?? "";
        const company = contact.company_name?.toLowerCase() ?? "";
        const tags = typeof contact.tags === "string"
          ? contact.tags.toLowerCase()
          : Array.isArray(contact.tags)
          ? contact.tags.join(" ").toLowerCase()
          : "";

        return (
          fullName.includes(query) ||
          phone.includes(query) ||
          email.includes(query) ||
          company.includes(query) ||
          tags.includes(query)
        );
      });
    }

    return filtered;
  }, [contacts, searchQuery, statusFilter]);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="shrink-0 p-6 border-b space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Users className="h-6 w-6 text-primary" />
            <h1 className="text-2xl font-bold">Contacts</h1>
            <Badge variant="secondary" className="text-sm">
              {contacts.length}
            </Badge>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" className="gap-2" onClick={() => setIsScrapeDialogOpen(true)}>
              <MapPin className="h-4 w-4" />
              Find Leads
            </Button>
            <Button variant="outline" className="gap-2" onClick={() => setIsImportDialogOpen(true)}>
              <Upload className="h-4 w-4" />
              Import CSV
            </Button>
            <Button className="gap-2" onClick={() => setIsCreateDialogOpen(true)}>
              <Plus className="h-4 w-4" />
              Add Contact
            </Button>
          </div>
        </div>

        {/* Bulk Actions Bar */}
        {isSelectionMode && (
          <div className="flex items-center gap-3 p-3 bg-muted/50 rounded-lg border">
            <Checkbox
              checked={selectedIds.length === filteredContacts.length && filteredContacts.length > 0}
              onCheckedChange={handleSelectAll}
            />
            <span className="text-sm font-medium">
              {selectedIds.length} selected
            </span>
            <div className="flex-1" />
            <Button
              variant="outline"
              size="sm"
              onClick={handleClearSelection}
              className="gap-2"
            >
              <X className="h-4 w-4" />
              Clear
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsBulkTagDialogOpen(true)}
              className="gap-2"
            >
              <Tags className="h-4 w-4" />
              Tag
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setIsDeleteDialogOpen(true)}
              className="gap-2"
              disabled={bulkDeleteMutation.isPending}
            >
              <Trash2 className="h-4 w-4" />
              Delete ({selectedIds.length})
            </Button>
          </div>
        )}

        {/* Search and Sort */}
        <div className="flex items-center gap-4">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search by name, email, phone, or company..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
          <Select value={sortBy} onValueChange={(value: ContactSortBy) => setSortBy(value)}>
            <SelectTrigger className="w-[180px]">
              <ArrowUpDown className="h-4 w-4 mr-2" />
              <SelectValue placeholder="Sort by" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="created_at">Newest First</SelectItem>
              <SelectItem value="unread_first">Unread First</SelectItem>
              <SelectItem value="last_conversation">Recent Activity</SelectItem>
            </SelectContent>
          </Select>
          {!isSelectionMode && filteredContacts.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setSelectedIds([filteredContacts[0].id])}
              className="gap-2"
            >
              <CheckSquare className="h-4 w-4" />
              Select
            </Button>
          )}
        </div>

        {/* Advanced Filters */}
        {workspaceId && (
          <ContactFilterBuilder
            workspaceId={workspaceId}
            filters={filters}
            onFiltersChange={setFilters}
          />
        )}

        {/* Status Filters */}
        <StatusFilter
          selectedStatus={statusFilter as ContactStatus | null}
          onStatusChange={setStatusFilter as (status: ContactStatus | null) => void}
          counts={statusCounts}
        />
      </div>

      {/* Contacts Grid */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="p-6">
          {isLoadingContacts ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {Array.from({ length: 8 }).map((_, i) => (
                <ContactCardSkeleton key={i} />
              ))}
            </div>
          ) : filteredContacts.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <User className="h-16 w-16 text-muted-foreground/50 mb-4" />
              <h3 className="text-lg font-medium mb-1">
                {searchQuery || statusFilter ? "No contacts found" : "No contacts yet"}
              </h3>
              <p className="text-sm text-muted-foreground mb-4">
                {searchQuery || statusFilter
                  ? "Try adjusting your search or filters"
                  : "Get started by adding your first contact"}
              </p>
              {!searchQuery && !statusFilter && (
                <Button className="gap-2" onClick={() => setIsCreateDialogOpen(true)}>
                  <Plus className="h-4 w-4" />
                  Add Contact
                </Button>
              )}
            </div>
          ) : (
            <AnimatePresence mode="popLayout">
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {filteredContacts.map((contact) => (
                  <ContactCard
                    key={contact.id}
                    contact={contact}
                    isSelected={selectedIds.includes(contact.id)}
                    onSelectChange={(checked) => handleSelectContact(contact.id, checked)}
                    isSelectionMode={isSelectionMode}
                  />
                ))}
              </div>
            </AnimatePresence>
          )}
        </div>
      </ScrollArea>

      <CreateContactDialog
        open={isCreateDialogOpen}
        onOpenChange={setIsCreateDialogOpen}
      />

      <ImportContactsDialog
        open={isImportDialogOpen}
        onOpenChange={setIsImportDialogOpen}
      />

      <ScrapeLeadsDialog
        open={isScrapeDialogOpen}
        onOpenChange={setIsScrapeDialogOpen}
      />

      {workspaceId && (
        <BulkTagDialog
          open={isBulkTagDialogOpen}
          onOpenChange={setIsBulkTagDialogOpen}
          selectedContactIds={selectedIds}
          workspaceId={workspaceId}
        />
      )}

      <AlertDialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {selectedIds.length} contact{selectedIds.length > 1 ? "s" : ""}?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. This will permanently delete the selected contact{selectedIds.length > 1 ? "s" : ""} and all associated data.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleBulkDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={bulkDeleteMutation.isPending}
            >
              {bulkDeleteMutation.isPending ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
