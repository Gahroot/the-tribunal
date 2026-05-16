import { DashboardPage } from "@/components/dashboard/dashboard-page";
import { AppSidebar } from "@/components/layout/app-sidebar";

export default function Dashboard() {
  return (
    <AppSidebar>
      <DashboardPage />
    </AppSidebar>
  );
}
