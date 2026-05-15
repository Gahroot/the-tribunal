import Link from "next/link";

import { Button } from "@/components/ui/button";
import { PageEmptyState } from "@/components/ui/page-state";

export default function NotFound() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <PageEmptyState
        title="Offer not found"
        description="This offer doesn't exist or is no longer available."
        action={
          <Button asChild variant="outline" size="sm">
            <Link href="/">Go home</Link>
          </Button>
        }
      />
    </div>
  );
}
