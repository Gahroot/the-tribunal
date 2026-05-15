import Link from "next/link";

import { Button } from "@/components/ui/button";
import { PageEmptyState } from "@/components/ui/page-state";

export default function NotFound() {
  return (
    <PageEmptyState
      title="Experiment not found"
      description="This experiment doesn't exist or you don't have access to it."
      action={
        <Button asChild variant="outline" size="sm">
          <Link href="/experiments">Back to experiments</Link>
        </Button>
      }
    />
  );
}
