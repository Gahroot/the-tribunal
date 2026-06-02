import { FileQuestion } from "lucide-react";
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { PageEmptyState } from "@/components/ui/page-state";

export default function NotFound() {
  return (
    <PageEmptyState
      className="min-h-screen bg-background"
      icon={<FileQuestion className="size-8" />}
      title="404 — Page not found"
      description="The page you are looking for does not exist."
      action={
        <Link href="/dashboard" className={buttonVariants()}>
          Back to Dashboard
        </Link>
      }
    />
  );
}
