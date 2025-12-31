import { AppSidebar } from "@/components/layout/app-sidebar";
import { CampaignForm } from "@/components/campaigns/campaign-form";

interface CampaignDetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function CampaignDetailPage({ params }: CampaignDetailPageProps) {
  const { id } = await params;

  return (
    <AppSidebar>
      <CampaignForm campaignId={id} />
    </AppSidebar>
  );
}
