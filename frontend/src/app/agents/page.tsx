import { AppSidebar } from "@/components/layout/app-sidebar";
import { AgentsList } from "@/components/agents/agents-list";

export default function AgentsPage() {
  return (
    <AppSidebar>
      <AgentsList />
    </AppSidebar>
  );
}
