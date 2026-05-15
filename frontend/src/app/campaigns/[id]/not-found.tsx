import Link from "next/link";

import { Button } from "@/components/ui/button";
import { PageEmptyState } from "@/components/ui/page-state";

export default function NotFound() {
  return (
    <PageEmptyState
      title="Campaign not found"
      description="This campaign doesn't exist or you don't have access to it."
      action={
        <Button asChild variant="outline" size="sm">
          <Link href="/campaigns">Back to campaigns</Link>
        </Button>
      }
    />
  );
}
