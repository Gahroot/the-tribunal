import Link from "next/link";

import { Button } from "@/components/ui/button";
import { PageEmptyState } from "@/components/ui/page-state";

export default function NotFound() {
  return (
    <PageEmptyState
      title="Offer not found"
      description="This offer doesn't exist or you don't have access to it."
      action={
        <Button asChild variant="outline" size="sm">
          <Link href="/offers">Back to offers</Link>
        </Button>
      }
    />
  );
}
