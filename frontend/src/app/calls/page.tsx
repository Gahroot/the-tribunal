import { CallsList } from "@/components/calls/calls-list";
import { AppSidebar } from "@/components/layout/app-sidebar";

export default function CallsPage() {
  return (
    <AppSidebar>
      <CallsList />
    </AppSidebar>
  );
}
