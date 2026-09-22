import { redirect } from "next/navigation";

/**
 * Single guided campaign-creation flow lives at /campaigns/sms/new
 * (Compose → Audience → Preview → send confirmation).
 */
export default function NewCampaignPage() {
  redirect("/campaigns/sms/new");
}
