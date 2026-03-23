"use client";

import { Search, ArrowUpDown } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { ContactFilterBuilder } from "@/components/filters/contact-filter-builder";
import { contactStatusColors, contactStatusLabels } from "@/lib/status-colors";
import type { ContactSortBy } from "@/lib/api/contacts";
import type { ContactStatus } from "@/types";
import type { FilterDefinition } from "@/types";

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

export interface ContactsToolbarProps {
  inputValue: string;
  onInputChange: (value: string) => void;
  sortBy: ContactSortBy;
  onSortByChange: (value: ContactSortBy) => void;
  workspaceId: string | null;
  filters: FilterDefinition | null;
  onFiltersChange: (filters: FilterDefinition | null) => void;
  statusFilter: string | null;
  onStatusChange: (status: ContactStatus | null) => void;
  statusCounts: Record<ContactStatus | "all", number>;
}

export function ContactsToolbar({
  inputValue,
  onInputChange,
  sortBy,
  onSortByChange,
  workspaceId,
  filters,
  onFiltersChange,
  statusFilter,
  onStatusChange,
  statusCounts,
}: ContactsToolbarProps) {
  return (
    <>
      {/* Search and Sort */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by name, email, phone, or company..."
            value={inputValue}
            onChange={(e) => onInputChange(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select value={sortBy} onValueChange={(value: ContactSortBy) => onSortByChange(value)}>
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
      </div>

      {/* Advanced Filters */}
      {workspaceId && (
        <ContactFilterBuilder
          workspaceId={workspaceId}
          filters={filters}
          onFiltersChange={onFiltersChange}
        />
      )}

      {/* Status Filters */}
      <StatusFilter
        selectedStatus={statusFilter as ContactStatus | null}
        onStatusChange={onStatusChange}
        counts={statusCounts}
      />
    </>
  );
}
