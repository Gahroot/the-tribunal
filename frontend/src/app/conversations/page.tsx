import { ConversationsPage } from "@/components/conversations/conversations-page";
import { AppSidebar } from "@/components/layout/app-sidebar";

export default function ConversationsRoute() {
  return (
    <AppSidebar>
      <div className="h-full overflow-hidden">
        <ConversationsPage />
      </div>
    </AppSidebar>
  );
}
