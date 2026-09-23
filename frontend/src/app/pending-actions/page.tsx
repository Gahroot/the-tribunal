import type { Metadata } from "next";

import { AppSidebar } from "@/components/layout/app-sidebar";
import { PendingActionsPage } from "@/components/pending-actions/pending-actions-page";

export const metadata: Metadata = {
  title: "Pending actions",
  description: "Review and approve AI agent actions before they run.",
};

export default function PendingActionsRoute() {
  return (
    <AppSidebar>
      <PendingActionsPage />
    </AppSidebar>
  );
}
