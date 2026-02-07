import { Loader2 } from "lucide-react";

export function ResourceListLoading() {
  return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="size-8 animate-spin text-muted-foreground" />
    </div>
  );
}
