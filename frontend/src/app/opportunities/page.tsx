import { AppSidebar } from "@/components/layout/app-sidebar";
import { OpportunitiesBoard } from "@/components/opportunities/opportunities-board";

export default function OpportunitiesRoute() {
  return (
    <AppSidebar>
      <div className="flex h-full flex-col overflow-hidden bg-neutral-100 dark:bg-neutral-950">
        <div className="p-6 pb-3">
          <h1 className="text-2xl font-semibold tracking-tight">Opportunities</h1>
          <p className="text-sm text-muted-foreground">
            Drag a deal to a new stage — or open its menu and pick a stage from
            the keyboard. Totals update as you move.
          </p>
        </div>
        <div className="min-h-0 flex-1 px-6 pb-6">
          <OpportunitiesBoard />
        </div>
      </div>
    </AppSidebar>
  );
}
