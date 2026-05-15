import Link from "next/link";

import { Button } from "@/components/ui/button";
import { PageEmptyState } from "@/components/ui/page-state";

export default function NotFound() {
  return (
    <PageEmptyState
      title="Contact not found"
      description="This contact doesn't exist or you don't have access to it."
      action={
        <Button asChild variant="outline" size="sm">
          <Link href="/contacts">Back to contacts</Link>
        </Button>
      }
    />
  );
}
