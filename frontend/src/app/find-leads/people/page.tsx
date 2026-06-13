import { AppSidebar } from "@/components/layout/app-sidebar";

import { PeopleSearchClient } from "./people-client";

export default function PeopleSearch() {
  return (
    <AppSidebar>
      <PeopleSearchClient />
    </AppSidebar>
  );
}
