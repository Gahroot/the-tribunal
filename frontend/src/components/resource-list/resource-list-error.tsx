import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ResourceListErrorProps {
  resourceName: string;
  onRetry: () => void;
}

export function ResourceListError({ resourceName, onRetry }: ResourceListErrorProps) {
  return (
    <div className="flex flex-col items-center justify-center h-64 gap-2">
      <AlertCircle className="size-8 text-destructive" />
      <p className="text-muted-foreground">Failed to load {resourceName}</p>
      <Button variant="outline" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}
