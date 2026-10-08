import { Suspense } from "react";

import { AppSidebar } from "@/components/layout/app-sidebar";
import { NudgesPage } from "@/components/nudges/nudges-page";

export default function Nudges() {
  return (
    <AppSidebar>
      <Suspense fallback={null}>
        <NudgesPage />
      </Suspense>
    </AppSidebar>
  );
}
