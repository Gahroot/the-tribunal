"use client";

import * as React from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { Search, Plus, User, Phone, Mail, Users } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useContactStore } from "@/lib/contact-store";
import { CreateContactDialog } from "@/components/contacts/create-contact-dialog";
import type { Contact, ContactStatus } from "@/types";

const statusColors: Record<string, string> = {
  new: "bg-blue-500/10 text-blue-500 hover:bg-blue-500/20",
  contacted: "bg-yellow-500/10 text-yellow-500 hover:bg-yellow-500/20",
  qualified: "bg-green-500/10 text-green-500 hover:bg-green-500/20",
  converted: "bg-purple-500/10 text-purple-500 hover:bg-purple-500/20",
  lost: "bg-red-500/10 text-red-500 hover:bg-red-500/20",
};

const statusLabels: Record<ContactStatus, string> = {
  new: "New",
  contacted: "Contacted",
  qualified: "Qualified",
  converted: "Converted",
  lost: "Lost",
};

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
}

function ContactCard({ contact }: ContactCardProps) {
  const displayName = [contact.first_name, contact.last_name].filter(Boolean).join(" ") || "Unknown";

  return (
    <Link href={`/contacts/${contact.id}`}>
      <motion.div
        layout
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.2 }}
        className={cn(
          "flex flex-col p-4 rounded-xl border bg-card",
          "hover:bg-accent/50 hover:border-accent transition-all cursor-pointer",
          "group"
        )}
      >
        <div className="flex items-start gap-3">
          <Avatar className="h-12 w-12 shrink-0">
            <AvatarFallback className="bg-primary/10 text-primary text-base font-medium">
              {getInitials(contact)}
            </AvatarFallback>
          </Avatar>

          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold truncate group-hover:text-primary transition-colors">
                {displayName}
              </span>
              <Badge variant="secondary" className={cn("text-xs shrink-0", statusColors[contact.status])}>
                {statusLabels[contact.status]}
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

        {contact.tags && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {(() => {
              const tagsArray = Array.isArray(contact.tags)
                ? contact.tags
                : typeof contact.tags === "string"
                  ? contact.tags.split(",").map((t) => t.trim()).filter(Boolean)
                  : [];

              return (
                <>
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
                </>
              );
            })()}
          </div>
        )}
      </motion.div>
    </Link>
  );
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
            status !== "all" && selectedStatus !== status && statusColors[status]
          )}
        >
          {status === "all" ? "All" : statusLabels[status]}
          <span className="text-xs opacity-70">({counts[status]})</span>
        </Button>
      ))}
    </div>
  );
}

export function ContactsPage() {
  const [isCreateDialogOpen, setIsCreateDialogOpen] = React.useState(false);
  const {
    contacts,
    searchQuery,
    setSearchQuery,
    statusFilter,
    setStatusFilter,
    isLoadingContacts,
  } = useContactStore();

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
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-6 border-b space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Users className="h-6 w-6 text-primary" />
            <h1 className="text-2xl font-bold">Contacts</h1>
            <Badge variant="secondary" className="text-sm">
              {contacts.length}
            </Badge>
          </div>
          <Button className="gap-2" onClick={() => setIsCreateDialogOpen(true)}>
            <Plus className="h-4 w-4" />
            Add Contact
          </Button>
        </div>

        {/* Search */}
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
        </div>

        {/* Status Filters */}
        <StatusFilter
          selectedStatus={statusFilter as ContactStatus | null}
          onStatusChange={setStatusFilter as (status: ContactStatus | null) => void}
          counts={statusCounts}
        />
      </div>

      {/* Contacts Grid */}
      <ScrollArea className="flex-1">
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
                  <ContactCard key={contact.id} contact={contact} />
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
    </div>
  );
}
