"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useMutation } from "@tanstack/react-query";
import {
  Search,
  Users,
  CheckCircle2,
  Circle,
  Filter,
  X,
  Loader2,
} from "lucide-react";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { useDebounce } from "@/hooks/useDebounce";
import { useInfiniteContacts } from "@/hooks/useInfiniteContacts";
import { contactsApi } from "@/lib/api/contacts";
import type { Contact, ContactStatus } from "@/types";

const ROW_HEIGHT = 72;
const OVERSCAN = 5;

interface VirtualContactSelectorProps {
  workspaceId: string;
  selectedIds: Set<number>;
  onSelectionChange: (ids: Set<number>) => void;
}

const statusColors: Record<ContactStatus, string> = {
  new: "bg-blue-500/10 text-blue-500",
  contacted: "bg-yellow-500/10 text-yellow-500",
  qualified: "bg-green-500/10 text-green-500",
  converted: "bg-purple-500/10 text-purple-500",
  lost: "bg-red-500/10 text-red-500",
};

export function VirtualContactSelector({
  workspaceId,
  selectedIds,
  onSelectionChange,
}: VirtualContactSelectorProps) {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<ContactStatus | "all">("all");
  const debouncedSearch = useDebounce(search, 300);

  const parentRef = useRef<HTMLDivElement>(null);

  const {
    contacts,
    total,
    isLoading,
    isFetchingNextPage,
    hasNextPage,
    fetchNextPage,
  } = useInfiniteContacts({
    workspaceId,
    search: debouncedSearch,
    status: statusFilter,
  });

  // Fetch IDs for selection (with optional limit)
  const selectMutation = useMutation({
    mutationFn: async (limit?: number) => {
      const params: { search?: string; status?: ContactStatus } = {};
      if (debouncedSearch) params.search = debouncedSearch;
      if (statusFilter !== "all") params.status = statusFilter;
      const result = await contactsApi.listIds(workspaceId, params);
      // Apply limit if specified
      if (limit && limit < result.ids.length) {
        return { ...result, ids: result.ids.slice(0, limit) };
      }
      return result;
    },
    onSuccess: (data) => {
      const newSelected = new Set(selectedIds);
      for (const id of data.ids) {
        newSelected.add(id);
      }
      onSelectionChange(newSelected);
    },
  });

  const virtualizer = useVirtualizer({
    count: contacts.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: OVERSCAN,
  });

  const virtualItems = virtualizer.getVirtualItems();

  // Fetch more when scrolling near bottom
  useEffect(() => {
    const lastItem = virtualItems[virtualItems.length - 1];
    if (!lastItem) return;

    if (
      lastItem.index >= contacts.length - 1 - OVERSCAN &&
      hasNextPage &&
      !isFetchingNextPage
    ) {
      fetchNextPage();
    }
  }, [virtualItems, contacts.length, hasNextPage, isFetchingNextPage, fetchNextPage]);

  const toggleContact = useCallback(
    (contactId: number) => {
      const newSelected = new Set(selectedIds);
      if (newSelected.has(contactId)) {
        newSelected.delete(contactId);
      } else {
        newSelected.add(contactId);
      }
      onSelectionChange(newSelected);
    },
    [selectedIds, onSelectionChange]
  );

  const handleQuickSelect = (value: string) => {
    if (value === "all") {
      selectMutation.mutate(undefined);
    } else {
      selectMutation.mutate(parseInt(value));
    }
  };

  const deselectAll = () => {
    onSelectionChange(new Set());
  };

  const formatPhone = (phone?: string) => {
    if (!phone) return "";
    const cleaned = phone.replace(/\D/g, "");
    if (cleaned.length === 10) {
      return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
    }
    if (cleaned.length === 11 && cleaned.startsWith("1")) {
      return `+1 (${cleaned.slice(1, 4)}) ${cleaned.slice(4, 7)}-${cleaned.slice(7)}`;
    }
    return phone;
  };

  const renderContactRow = (contact: Contact) => {
    const isSelected = selectedIds.has(contact.id);
    const fullName = [contact.first_name, contact.last_name]
      .filter(Boolean)
      .join(" ");

    return (
      <div
        onClick={() => toggleContact(contact.id)}
        className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-colors h-[${ROW_HEIGHT}px] ${
          isSelected
            ? "bg-primary/10 border border-primary/30"
            : "hover:bg-muted/50"
        }`}
      >
        <div className="flex-shrink-0">
          {isSelected ? (
            <CheckCircle2 className="size-5 text-primary" />
          ) : (
            <Circle className="size-5 text-muted-foreground" />
          )}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium truncate">
              {fullName || "Unknown"}
            </span>
            <Badge
              variant="secondary"
              className={`text-xs ${statusColors[contact.status]}`}
            >
              {contact.status}
            </Badge>
          </div>
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            {contact.phone_number && (
              <span>{formatPhone(contact.phone_number)}</span>
            )}
            {contact.email && (
              <span className="truncate">{contact.email}</span>
            )}
          </div>
          {contact.company_name && (
            <div className="text-xs text-muted-foreground mt-0.5">
              {contact.company_name}
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      {/* Header with stats */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users className="size-5 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">
            {selectedIds.size} of {total} selected
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Select
            value=""
            onValueChange={handleQuickSelect}
            disabled={total === 0 || selectMutation.isPending}
          >
            <SelectTrigger className="w-36">
              {selectMutation.isPending ? (
                <>
                  <Loader2 className="size-4 mr-2 animate-spin" />
                  Selecting...
                </>
              ) : (
                <SelectValue placeholder="Select..." />
              )}
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="100">Select 100</SelectItem>
              <SelectItem value="250">Select 250</SelectItem>
              <SelectItem value="500">Select 500</SelectItem>
              <SelectItem value="1000">Select 1,000</SelectItem>
              <SelectItem value="all">Select All ({total.toLocaleString()})</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="sm"
            onClick={deselectAll}
            disabled={selectedIds.size === 0}
          >
            Clear
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground" />
          <Input
            placeholder="Search by name, email, phone..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
          {search && (
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-1 top-1/2 -translate-y-1/2 size-7"
              onClick={() => setSearch("")}
            >
              <X className="size-4" />
            </Button>
          )}
        </div>
        <Select
          value={statusFilter}
          onValueChange={(v) => setStatusFilter(v as ContactStatus | "all")}
        >
          <SelectTrigger className="w-40">
            <Filter className="size-4 mr-2" />
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Statuses</SelectItem>
            <SelectItem value="new">New</SelectItem>
            <SelectItem value="contacted">Contacted</SelectItem>
            <SelectItem value="qualified">Qualified</SelectItem>
            <SelectItem value="converted">Converted</SelectItem>
            <SelectItem value="lost">Lost</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Virtual Contact List */}
      <div
        ref={parentRef}
        className="h-[400px] border rounded-lg overflow-auto"
      >
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="flex flex-col items-center gap-2 text-muted-foreground">
              <Loader2 className="size-8 animate-spin" />
              <span>Loading contacts...</span>
            </div>
          </div>
        ) : contacts.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
            <Users className="size-12 mb-2 opacity-50" />
            <p>No contacts found</p>
            {search && (
              <Button
                variant="link"
                onClick={() => setSearch("")}
                className="mt-1"
              >
                Clear search
              </Button>
            )}
          </div>
        ) : (
          <div
            style={{
              height: `${virtualizer.getTotalSize()}px`,
              width: "100%",
              position: "relative",
            }}
          >
            <div className="p-2">
              {virtualItems.map((virtualRow) => {
                const contact = contacts[virtualRow.index];
                return (
                  <div
                    key={contact.id}
                    style={{
                      position: "absolute",
                      top: 0,
                      left: 0,
                      width: "100%",
                      height: `${virtualRow.size}px`,
                      transform: `translateY(${virtualRow.start}px)`,
                      padding: "0 8px",
                    }}
                  >
                    {renderContactRow(contact)}
                  </div>
                );
              })}
            </div>

            {isFetchingNextPage && (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="size-6 animate-spin text-muted-foreground" />
              </div>
            )}
          </div>
        )}
      </div>

      {/* Selected summary */}
      {selectedIds.size > 0 && (
        <div className="flex items-center gap-2 p-3 bg-primary/5 rounded-lg border border-primary/20">
          <CheckCircle2 className="size-5 text-primary" />
          <span className="text-sm font-medium">
            {selectedIds.size} contact{selectedIds.size !== 1 ? "s" : ""} selected
          </span>
        </div>
      )}
    </div>
  );
}
