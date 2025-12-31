import { AppSidebar } from "@/components/layout/app-sidebar";
import { CampaignsList } from "@/components/campaigns/campaigns-list";

export default function CampaignsPage() {
  return (
    <AppSidebar>
      <CampaignsList />
    </AppSidebar>
  );
}
