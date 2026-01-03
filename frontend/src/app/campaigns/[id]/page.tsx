import { AppSidebar } from "@/components/layout/app-sidebar";
import { CampaignDetail } from "@/components/campaigns/campaign-detail";

interface CampaignDetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function CampaignDetailPage({ params }: CampaignDetailPageProps) {
  const { id } = await params;

  return (
    <AppSidebar>
      <CampaignDetail campaignId={id} />
    </AppSidebar>
  );
}
