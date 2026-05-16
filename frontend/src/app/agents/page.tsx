import { AgentsList } from "@/components/agents/agents-list";
import { AppSidebar } from "@/components/layout/app-sidebar";

export default function AgentsPage() {
  return (
    <AppSidebar>
      <AgentsList />
    </AppSidebar>
  );
}
