import { AppSidebar } from "@/components/layout/app-sidebar";
import { CallsList } from "@/components/calls/calls-list";

export default function CallsPage() {
  return (
    <AppSidebar>
      <CallsList />
    </AppSidebar>
  );
}
