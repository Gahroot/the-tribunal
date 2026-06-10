import { CallsList } from "@/components/calls/calls-list";
import { LiveCallsPanel } from "@/components/calls/live-calls-panel";
import { AppSidebar } from "@/components/layout/app-sidebar";

export default function CallsPage() {
  return (
    <AppSidebar>
      <div className="space-y-4">
        <LiveCallsPanel />
        <CallsList />
      </div>
    </AppSidebar>
  );
}
