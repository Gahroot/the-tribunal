import { Suspense } from "react";


import { ConversationsPage } from "@/components/conversations/conversations-page";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { PageLoadingState } from "@/components/ui/page-state";

export default function ConversationsRoute() {
  return (
    <AppSidebar>
      <div className="h-full overflow-hidden">
        <Suspense fallback={<PageLoadingState message="Loading inbox" />}>
          <ConversationsPage />
        </Suspense>
      </div>
    </AppSidebar>
  );
}
