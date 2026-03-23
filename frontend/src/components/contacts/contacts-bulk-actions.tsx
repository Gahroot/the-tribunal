"use client";

import { X, Square, Tags, Trash2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { contactStatusLabels, contactStatusDotColors } from "@/lib/status-colors";
import type { ContactStatus } from "@/types";

const ALL_STATUSES: ContactStatus[] = ["new", "contacted", "qualified", "converted", "lost"];

export interface ContactsBulkActionsProps {
  selectedCount: number;
  selectAllMatchingIds: Set<number> | null;
  allVisibleSelected: boolean;
  someVisibleSelected: boolean;
  showSelectAllMatching: boolean;
  hasActiveFilters: boolean;
  contactsTotal: number;
  visibleCount: number;
  isFetchingAllIds: boolean;
  isBulkUpdatePending: boolean;
  isBulkDeletePending: boolean;
  onSelectAllVisible: () => void;
  onClearSelection: () => void;
  onSelectAllMatching: () => void;
  onBulkStatusChange: (status: ContactStatus) => void;
  onOpenTagDialog: () => void;
  onOpenDeleteDialog: () => void;
}

export function ContactsBulkActions({
  selectedCount,
  selectAllMatchingIds,
  allVisibleSelected,
  someVisibleSelected,
  showSelectAllMatching,
  hasActiveFilters,
  contactsTotal,
  visibleCount,
  isFetchingAllIds,
  isBulkUpdatePending,
  isBulkDeletePending,
  onSelectAllVisible,
  onClearSelection,
  onSelectAllMatching,
  onBulkStatusChange,
  onOpenTagDialog,
  onOpenDeleteDialog,
}: ContactsBulkActionsProps) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3 p-3 bg-primary/5 rounded-lg border border-primary/20">
        <Checkbox
          checked={allVisibleSelected ? true : someVisibleSelected ? "indeterminate" : false}
          onCheckedChange={onSelectAllVisible}
        />
        <span className="text-sm font-medium">
          {selectedCount === 0
            ? "Select contacts"
            : selectAllMatchingIds
              ? `All ${selectedCount} matching contacts selected`
              : `${selectedCount} selected`}
        </span>
        <div className="flex-1" />
        {selectedCount > 0 && (
          <>
            <Button
              variant="ghost"
              size="sm"
              onClick={onClearSelection}
              className="gap-1.5 text-muted-foreground"
            >
              <X className="h-3.5 w-3.5" />
              Clear
            </Button>
            <div className="h-4 w-px bg-border" />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="gap-2"
                  disabled={isBulkUpdatePending}
                >
                  {isBulkUpdatePending
                    ? <RefreshCw className="h-4 w-4 animate-spin" />
                    : <Square className="h-4 w-4" />}
                  Status
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                {ALL_STATUSES.map((status) => (
                  <DropdownMenuItem
                    key={status}
                    onClick={() => onBulkStatusChange(status)}
                  >
                    <span className={cn("h-2 w-2 rounded-full mr-2", contactStatusDotColors[status])} />
                    {contactStatusLabels[status]}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
            <Button
              variant="outline"
              size="sm"
              onClick={onOpenTagDialog}
              className="gap-2"
            >
              <Tags className="h-4 w-4" />
              Tag
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={onOpenDeleteDialog}
              className="gap-2"
              disabled={isBulkDeletePending}
            >
              <Trash2 className="h-4 w-4" />
              Delete
            </Button>
          </>
        )}
      </div>

      {/* "Select all matching" banner */}
      {showSelectAllMatching && (
        <div className="flex items-center justify-center gap-2 py-2 px-3 bg-muted/50 rounded-lg border text-sm">
          <span className="text-muted-foreground">
            All {visibleCount} contacts on this page are selected.
          </span>
          <Button
            variant="link"
            size="sm"
            className="h-auto p-0 text-primary font-medium"
            onClick={onSelectAllMatching}
            disabled={isFetchingAllIds}
          >
            {isFetchingAllIds
              ? "Loading..."
              : hasActiveFilters
                ? "Select all contacts matching current filters"
                : `Select all ${contactsTotal} contacts`}
          </Button>
        </div>
      )}

      {/* "All matching selected" banner */}
      {selectAllMatchingIds && (
        <div className="flex items-center justify-center gap-2 py-2 px-3 bg-primary/5 rounded-lg border border-primary/20 text-sm">
          <span className="font-medium text-primary">
            All {selectAllMatchingIds.size} matching contacts are selected.
          </span>
          <Button
            variant="link"
            size="sm"
            className="h-auto p-0"
            onClick={onClearSelection}
          >
            Clear selection
          </Button>
        </div>
      )}
    </div>
  );
}
