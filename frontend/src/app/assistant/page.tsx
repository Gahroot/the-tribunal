import { AppSidebar } from "@/components/layout/app-sidebar";
import { AssistantChat } from "@/components/assistant/assistant-chat";

export default function AssistantPage() {
  return (
    <AppSidebar>
      <div className="flex h-full flex-col">
        <div className="border-b px-6 py-4">
          <h1 className="text-xl font-semibold">CRM Assistant</h1>
          <p className="text-sm text-muted-foreground">
            Your personal AI assistant for managing contacts, campaigns, and
            conversations.
          </p>
        </div>
        <AssistantChat className="flex-1" />
      </div>
    </AppSidebar>
  );
}
