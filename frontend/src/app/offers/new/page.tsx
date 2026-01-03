"use client";

import { AppSidebar } from "@/components/layout/app-sidebar";
import { OfferBuilderWizard } from "@/components/offers/offer-builder-wizard";
import { useAuth } from "@/providers/auth-provider";
import { Card, CardContent } from "@/components/ui/card";

export default function CreateOfferPage() {
  const { workspaceId } = useAuth();

  if (!workspaceId) {
    return (
      <AppSidebar>
        <div className="p-6">
          <Card>
            <CardContent className="p-6">
              <p className="text-muted-foreground">Loading workspace...</p>
            </CardContent>
          </Card>
        </div>
      </AppSidebar>
    );
  }

  return (
    <AppSidebar>
      <div className="p-6 max-w-4xl mx-auto">
        <div className="mb-6">
          <h1 className="text-2xl font-bold">Create Offer</h1>
          <p className="text-muted-foreground">
            Build an irresistible offer with value stacking
          </p>
        </div>
        <OfferBuilderWizard workspaceId={workspaceId} />
      </div>
    </AppSidebar>
  );
}
