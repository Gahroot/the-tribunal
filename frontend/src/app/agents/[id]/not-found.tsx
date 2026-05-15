import Link from "next/link";

import { Button } from "@/components/ui/button";
import { PageEmptyState } from "@/components/ui/page-state";

export default function NotFound() {
  return (
    <PageEmptyState
      title="Agent not found"
      description="This agent doesn't exist or you don't have access to it."
      action={
        <Button asChild variant="outline" size="sm">
          <Link href="/agents">Back to agents</Link>
        </Button>
      }
    />
  );
}
