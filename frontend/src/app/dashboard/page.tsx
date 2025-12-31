import { AppSidebar } from "@/components/layout/app-sidebar";
import { DashboardPage } from "@/components/dashboard/dashboard-page";

export default function Dashboard() {
  return (
    <AppSidebar>
      <DashboardPage />
    </AppSidebar>
  );
}
