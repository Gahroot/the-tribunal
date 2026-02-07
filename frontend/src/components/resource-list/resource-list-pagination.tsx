import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ResourceListPaginationProps {
  filteredCount: number;
  totalCount: number;
  resourceName: string;
}

export function ResourceListPagination({
  filteredCount,
  totalCount,
  resourceName,
}: ResourceListPaginationProps) {
  return (
    <div className="flex items-center justify-between">
      <div className="text-sm text-muted-foreground">
        Showing {filteredCount} of {totalCount} {resourceName}
      </div>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" disabled>
          <ChevronLeft className="size-4" />
          Previous
        </Button>
        <Button variant="outline" size="sm" disabled>
          Next
          <ChevronRight className="size-4" />
        </Button>
      </div>
    </div>
  );
}
