"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import {
  Tag,
  Percent,
  DollarSign,
  Gift,
  Check,
  Plus,
  Calendar,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Offer, DiscountType } from "@/types";

interface OfferSelectorProps {
  offers: Offer[];
  selectedId?: string;
  onSelect: (offerId: string | undefined) => void;
  onCreateOffer?: (offer: Partial<Offer>) => Promise<void>;
}

const discountTypeIcons: Record<DiscountType, React.ReactNode> = {
  percentage: <Percent className="size-4" />,
  fixed: <DollarSign className="size-4" />,
  free_service: <Gift className="size-4" />,
};

const discountTypeLabels: Record<DiscountType, string> = {
  percentage: "Percentage Off",
  fixed: "Fixed Amount",
  free_service: "Free Service",
};

export function OfferSelector({
  offers,
  selectedId,
  onSelect,
  onCreateOffer,
}: OfferSelectorProps) {
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newOffer, setNewOffer] = useState<Partial<Offer>>({
    name: "",
    description: "",
    discount_type: "percentage",
    discount_value: 0,
    terms: "",
    is_active: true,
  });
  const [isCreating, setIsCreating] = useState(false);

  const formatDiscount = (offer: Offer) => {
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
  };

  const handleCreate = async () => {
    if (!onCreateOffer || !newOffer.name) return;
    setIsCreating(true);
    try {
      await onCreateOffer(newOffer);
      setShowCreateDialog(false);
      setNewOffer({
        name: "",
        description: "",
        discount_type: "percentage",
        discount_value: 0,
        terms: "",
        is_active: true,
      });
    } finally {
      setIsCreating(false);
    }
  };

  const activeOffers = offers.filter((o) => o.is_active);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Tag className="size-4" />
          <span>Pair an offer with your campaign ({activeOffers.length} available)</span>
        </div>

        {onCreateOffer && (
          <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
            <DialogTrigger asChild>
              <Button variant="outline" size="sm">
                <Plus className="size-4 mr-1" />
                Create Offer
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create New Offer</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="offer-name">Offer Name</Label>
                  <Input
                    id="offer-name"
                    placeholder="e.g., Summer Sale 20% Off"
                    value={newOffer.name}
                    onChange={(e) =>
                      setNewOffer({ ...newOffer, name: e.target.value })
                    }
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Discount Type</Label>
                    <Select
                      value={newOffer.discount_type}
                      onValueChange={(v) =>
                        setNewOffer({
                          ...newOffer,
                          discount_type: v as DiscountType,
                        })
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="percentage">Percentage</SelectItem>
                        <SelectItem value="fixed">Fixed Amount</SelectItem>
                        <SelectItem value="free_service">Free Service</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="discount-value">
                      {newOffer.discount_type === "percentage"
                        ? "Percentage"
                        : "Amount ($)"}
                    </Label>
                    <Input
                      id="discount-value"
                      type="number"
                      min="0"
                      value={newOffer.discount_value}
                      onChange={(e) =>
                        setNewOffer({
                          ...newOffer,
                          discount_value: parseFloat(e.target.value) || 0,
                        })
                      }
                      disabled={newOffer.discount_type === "free_service"}
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="offer-description">Description</Label>
                  <Textarea
                    id="offer-description"
                    placeholder="Brief description of the offer..."
                    value={newOffer.description}
                    onChange={(e) =>
                      setNewOffer({ ...newOffer, description: e.target.value })
                    }
                    rows={2}
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="offer-terms">Terms & Conditions</Label>
                  <Textarea
                    id="offer-terms"
                    placeholder="e.g., Valid for new customers only..."
                    value={newOffer.terms}
                    onChange={(e) =>
                      setNewOffer({ ...newOffer, terms: e.target.value })
                    }
                    rows={2}
                  />
                </div>

                <Button
                  onClick={handleCreate}
                  disabled={!newOffer.name || isCreating}
                  className="w-full"
                >
                  {isCreating ? "Creating..." : "Create Offer"}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        )}
      </div>

      <ScrollArea className="h-[300px]">
        <div className="space-y-2 pr-4">
          {/* No offer option */}
          <motion.div
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.99 }}
            onClick={() => onSelect(undefined)}
            className={`relative p-4 rounded-lg border-2 cursor-pointer transition-colors ${
              !selectedId
                ? "border-primary bg-primary/5"
                : "border-border hover:border-primary/50"
            }`}
          >
            {!selectedId && (
              <div className="absolute top-3 right-3">
                <div className="size-5 rounded-full bg-primary flex items-center justify-center">
                  <Check className="size-3 text-primary-foreground" />
                </div>
              </div>
            )}
            <div className="flex items-center gap-3">
              <div className="size-10 rounded-full bg-muted flex items-center justify-center">
                <Tag className="size-5 text-muted-foreground" />
              </div>
              <div>
                <div className="font-medium">No Offer</div>
                <div className="text-sm text-muted-foreground">
                  Send campaign without a special offer
                </div>
              </div>
            </div>
          </motion.div>

          {/* Offer cards */}
          {activeOffers.map((offer) => {
            const isSelected = selectedId === offer.id;

            return (
              <motion.div
                key={offer.id}
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.99 }}
                onClick={() => onSelect(offer.id)}
                className={`relative p-4 rounded-lg border-2 cursor-pointer transition-colors ${
                  isSelected
                    ? "border-primary bg-primary/5"
                    : "border-border hover:border-primary/50"
                }`}
              >
                {isSelected && (
                  <div className="absolute top-3 right-3">
                    <div className="size-5 rounded-full bg-primary flex items-center justify-center">
                      <Check className="size-3 text-primary-foreground" />
                    </div>
                  </div>
                )}

                <div className="flex items-start gap-3">
                  <div className="size-10 rounded-full bg-gradient-to-br from-green-500/20 to-green-500/5 flex items-center justify-center text-green-600">
                    {discountTypeIcons[offer.discount_type]}
                  </div>

                  <div className="flex-1 min-w-0 pr-6">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium">{offer.name}</span>
                      <Badge variant="secondary" className="bg-green-500/10 text-green-600">
                        {formatDiscount(offer)}
                      </Badge>
                    </div>

                    {offer.description && (
                      <p className="text-sm text-muted-foreground mt-1 line-clamp-1">
                        {offer.description}
                      </p>
                    )}

                    {(offer.valid_from || offer.valid_until) && (
                      <div className="flex items-center gap-1 mt-2 text-xs text-muted-foreground">
                        <Calendar className="size-3" />
                        {offer.valid_from && (
                          <span>
                            From {new Date(offer.valid_from).toLocaleDateString()}
                          </span>
                        )}
                        {offer.valid_until && (
                          <span>
                            to {new Date(offer.valid_until).toLocaleDateString()}
                          </span>
                        )}
                      </div>
                    )}

                    {offer.terms && (
                      <div className="mt-2 text-xs text-muted-foreground italic line-clamp-1">
                        {offer.terms}
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            );
          })}

          {activeOffers.length === 0 && (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Tag className="size-12 mb-2 opacity-50" />
              <p>No offers available</p>
              {onCreateOffer && (
                <Button
                  variant="link"
                  onClick={() => setShowCreateDialog(true)}
                  className="mt-1"
                >
                  Create your first offer
                </Button>
              )}
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Insert offer text helper */}
      {selectedId && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="p-3 bg-green-500/5 rounded-lg border border-green-500/20 text-sm"
        >
          <p className="text-green-700 dark:text-green-400">
            Use these placeholders in your message:
          </p>
          <code className="text-xs bg-muted px-1 py-0.5 rounded mt-1 inline-block">
            {"{offer_name}"} {"{offer_discount}"} {"{offer_terms}"}
          </code>
        </motion.div>
      )}
    </div>
  );
}
