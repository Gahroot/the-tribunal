"use client";

import { use } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ArrowLeft, AlertCircle, Loader2 } from "lucide-react";

import { AppSidebar } from "@/components/layout/app-sidebar";
import { OfferBuilderWizard } from "@/components/offers/offer-builder-wizard";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { offersApi } from "@/lib/api/offers";
import { useWorkspaceId } from "@/hooks/use-workspace-id";

interface EditOfferPageProps {
  params: Promise<{ id: string }>;
}

export default function EditOfferPage({ params }: EditOfferPageProps) {
  const { id: offerId } = use(params);
  const workspaceId = useWorkspaceId();

  const {
    data: offer,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["offers", workspaceId, offerId],
    queryFn: () => offersApi.getWithLeadMagnets(workspaceId!, offerId),
    enabled: !!workspaceId,
  });

  if (isLoading) {
    return (
      <AppSidebar>
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </AppSidebar>
    );
  }

  if (error || !offer) {
    return (
      <AppSidebar>
        <div className="space-y-6 p-6">
          <Button variant="ghost" asChild>
            <Link href="/offers">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Offers
            </Link>
          </Button>
          <Card className="border-destructive">
            <CardContent className="flex flex-col items-center justify-center py-16">
              <AlertCircle className="mb-4 h-16 w-16 text-destructive" />
              <h3 className="mb-2 text-lg font-semibold">Error loading offer</h3>
              <p className="mb-4 text-center text-sm text-muted-foreground">
                {error instanceof Error ? error.message : "Failed to load offer details"}
              </p>
              <Button asChild>
                <Link href="/offers">Return to Offers</Link>
              </Button>
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
          <Button variant="ghost" size="sm" asChild className="mb-2">
            <Link href="/offers">
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Offers
            </Link>
          </Button>
          <h1 className="text-2xl font-bold">Edit Offer</h1>
          <p className="text-muted-foreground">
            Update your offer details and value stack
          </p>
        </div>
        <OfferBuilderWizard
          workspaceId={workspaceId!}
          existingOffer={offer}
        />
      </div>
    </AppSidebar>
  );
}
