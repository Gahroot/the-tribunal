import { PageErrorState } from "@/components/ui/page-state";

interface ResourceListErrorProps {
  resourceName: string;
  onRetry: () => void;
}

export function ResourceListError({ resourceName, onRetry }: ResourceListErrorProps) {
  return (
    <PageErrorState
      className="min-h-0 h-64"
      message={`Failed to load ${resourceName}`}
      onRetry={onRetry}
      retryLabel="Retry"
    />
  );
}
