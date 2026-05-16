import { AppSidebar } from "@/components/layout/app-sidebar";

import { OpportunitiesClient } from "./opportunities-client";

export default function Page() {
  return (
    <AppSidebar>
      <div className="h-full overflow-hidden">
        <OpportunitiesClient />
      </div>
    </AppSidebar>
  );
}
