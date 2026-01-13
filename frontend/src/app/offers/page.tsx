"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  Plus,
  Tag,
  Percent,
  DollarSign,
  Gift,
  MoreHorizontal,
  Edit,
  Trash2,
  Copy,
  Eye,
  Layers,
} from "lucide-react";

import { AppSidebar } from "@/components/layout/app-sidebar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Skeleton } from "@/components/ui/skeleton";

import { offersApi } from "@/lib/api/offers";
import { useWorkspaceId } from "@/hooks/use-workspace-id";
import type { Offer, DiscountType } from "@/types";

const discountTypeIcons: Record<DiscountType, React.ReactNode> = {
  percentage: <Percent className="size-4" />,
  fixed: <DollarSign className="size-4" />,
  free_service: <Gift className="size-4" />,
};

function formatDiscount(offer: Offer) {
  switch (offer.discount_type) {
    case "percentage":
      return `${offer.discount_value}% off`;
    case "fixed":
      return `$${offer.discount_value} off`;
    case "free_service":
      return "Free";
    default:
      return "";
  }
}

export default function OffersPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();

  const [deleteOfferId, setDeleteOfferId] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["offers", workspaceId],
    queryFn: () => offersApi.list(workspaceId!),
    enabled: !!workspaceId,
  });

  const deleteMutation = useMutation({
    mutationFn: (offerId: string) => offersApi.delete(workspaceId!, offerId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["offers", workspaceId] });
      setDeleteOfferId(null);
    },
  });

  const offers = data?.items || [];
  const activeOffers = offers.filter((o) => o.is_active);

  return (
    <AppSidebar>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Offers</h1>
            <p className="text-muted-foreground">
              Create irresistible offers with value stacking
            </p>
          </div>
          <Button onClick={() => router.push("/offers/new")}>
            <Plus className="size-4 mr-2" />
            Create Offer
          </Button>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Total Offers
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold">{offers.length}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Active Offers
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold text-green-600">
                {activeOffers.length}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                With Lead Magnets
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold text-blue-600">
                {offers.filter((o) => o.lead_magnets && o.lead_magnets.length > 0).length}
              </p>
            </CardContent>
          </Card>
        </div>

        {/* Offers List */}
        {isLoading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-32 w-full" />
            ))}
          </div>
        ) : offers.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center justify-center py-12">
              <Tag className="size-12 text-muted-foreground mb-4" />
              <h3 className="text-lg font-semibold mb-2">No offers yet</h3>
              <p className="text-muted-foreground text-center mb-4">
                Create your first irresistible offer with value stacking
              </p>
              <Button onClick={() => router.push("/offers/new")}>
                <Plus className="size-4 mr-2" />
                Create Your First Offer
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            {offers.map((offer) => (
              <motion.div
                key={offer.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
              >
                <Card className={!offer.is_active ? "opacity-60" : ""}>
                  <CardContent className="p-6">
                    <div className="flex items-start justify-between">
                      <div className="flex items-start gap-4">
                        <div className="size-12 rounded-full bg-gradient-to-br from-green-500/20 to-green-500/5 flex items-center justify-center text-green-600">
                          {discountTypeIcons[offer.discount_type]}
                        </div>
                        <div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <h3 className="font-semibold text-lg">{offer.name}</h3>
                            <Badge
                              variant="secondary"
                              className="bg-green-500/10 text-green-600"
                            >
                              {formatDiscount(offer)}
                            </Badge>
                            {!offer.is_active && (
                              <Badge variant="secondary">Inactive</Badge>
                            )}
                            {offer.value_stack_items && offer.value_stack_items.length > 0 && (
                              <Badge variant="outline" className="gap-1">
                                <Layers className="size-3" />
                                {offer.value_stack_items.length} items
                              </Badge>
                            )}
                            {offer.lead_magnets && offer.lead_magnets.length > 0 && (
                              <Badge variant="outline" className="gap-1 text-blue-600 border-blue-600/30">
                                <Gift className="size-3" />
                                {offer.lead_magnets.length} bonuses
                              </Badge>
                            )}
                          </div>
                          {offer.headline && (
                            <p className="font-medium text-muted-foreground mt-1">
                              {offer.headline}
                            </p>
                          )}
                          {offer.description && (
                            <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
                              {offer.description}
                            </p>
                          )}
                          {offer.total_value && offer.total_value > 0 && (
                            <p className="text-sm text-green-600 mt-2">
                              Total Value: ${offer.total_value.toLocaleString()}
                              {offer.offer_price && (
                                <span className="text-muted-foreground">
                                  {" "}
                                  • Your Price: ${offer.offer_price.toLocaleString()}
                                </span>
                              )}
                            </p>
                          )}
                        </div>
                      </div>

                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon">
                            <MoreHorizontal className="size-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            onClick={() =>
                              router.push(`/offers/${offer.id}`)
                            }
                          >
                            <Edit className="size-4 mr-2" />
                            Edit
                          </DropdownMenuItem>
                          <DropdownMenuItem>
                            <Eye className="size-4 mr-2" />
                            Preview
                          </DropdownMenuItem>
                          <DropdownMenuItem>
                            <Copy className="size-4 mr-2" />
                            Duplicate
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={() => setDeleteOfferId(offer.id)}
                          >
                            <Trash2 className="size-4 mr-2" />
                            Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            ))}
          </div>
        )}
      </div>

      {/* Delete Confirmation */}
      <AlertDialog
        open={!!deleteOfferId}
        onOpenChange={() => setDeleteOfferId(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Offer</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this offer? This action cannot be
              undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteOfferId && deleteMutation.mutate(deleteOfferId)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </AppSidebar>
  );
}
