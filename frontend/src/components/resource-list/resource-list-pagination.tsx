import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ResourceListPaginationProps {
  filteredCount: number;
  totalCount: number;
  resourceName: string;
  // Optional for functional pagination
  page?: number;
  totalPages?: number;
  onPageChange?: (page: number) => void;
}

export function ResourceListPagination({
  filteredCount,
  totalCount,
  resourceName,
  page,
  totalPages,
  onPageChange,
}: ResourceListPaginationProps) {
  return (
    <div className="flex items-center justify-between">
      <div className="text-sm text-muted-foreground">
        Showing {filteredCount} of {totalCount} {resourceName}
      </div>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          disabled={!onPageChange || !page || page <= 1}
          onClick={() => onPageChange && page && onPageChange(page - 1)}
        >
          <ChevronLeft className="size-4" />
          Previous
        </Button>
        {page && totalPages && (
          <span className="text-sm text-muted-foreground px-1">
            {page} / {totalPages}
          </span>
        )}
        <Button
          variant="outline"
          size="sm"
          disabled={!onPageChange || !page || !totalPages || page >= totalPages}
          onClick={() => onPageChange && page && onPageChange(page + 1)}
        >
          Next
          <ChevronRight className="size-4" />
        </Button>
      </div>
    </div>
  );
}
