import { CampaignForm } from "@/components/campaigns/campaign-form";
import { AppSidebar } from "@/components/layout/app-sidebar";

export default function NewCampaignPage() {
  return (
    <AppSidebar>
      <CampaignForm />
    </AppSidebar>
  );
}
