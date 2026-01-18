"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  FileText,
  DollarSign,
  Layers,
  Gift,
  Shield,
  Clock,
  Eye,
  ChevronLeft,
  ChevronRight,
  Check,
  Loader2,
  Globe,
  Copy,
  ExternalLink,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Checkbox } from "@/components/ui/checkbox";

import { ValueStackBuilder } from "./value-stack-builder";
import { LeadMagnetSelector } from "./lead-magnet-selector";
import { OfferPreview } from "./offer-preview";
import { AIOfferWriter } from "./ai-offer-writer";

import { offersApi, CreateOfferRequest } from "@/lib/api/offers";
import { leadMagnetsApi } from "@/lib/api/lead-magnets";
import type {
  Offer,
  DiscountType,
  GuaranteeType,
  UrgencyType,
  ValueStackItem,
  LeadMagnet,
} from "@/types";

interface OfferBuilderWizardProps {
  workspaceId: string;
  existingOffer?: Offer;
  onSuccess?: (offer: Offer) => void;
}

interface Step {
  id: string;
  label: string;
  icon: React.ReactNode;
}

const STEPS: Step[] = [
  { id: "basics", label: "Basics", icon: <FileText className="size-4" /> },
  { id: "pricing", label: "Pricing", icon: <DollarSign className="size-4" /> },
  { id: "value-stack", label: "Value Stack", icon: <Layers className="size-4" /> },
  { id: "lead-magnets", label: "Lead Magnets", icon: <Gift className="size-4" /> },
  { id: "guarantee", label: "Guarantee", icon: <Shield className="size-4" /> },
  { id: "urgency", label: "Urgency", icon: <Clock className="size-4" /> },
  { id: "publish", label: "Publish", icon: <Globe className="size-4" /> },
  { id: "review", label: "Review", icon: <Eye className="size-4" /> },
];

interface FormData {
  name: string;
  description: string;
  headline: string;
  subheadline: string;
  discount_type: DiscountType;
  discount_value: number;
  regular_price: number;
  offer_price: number;
  savings_amount: number;
  value_stack_items: ValueStackItem[];
  lead_magnet_ids: string[];
  guarantee_type: GuaranteeType | "";
  guarantee_days: number;
  guarantee_text: string;
  urgency_type: UrgencyType | "";
  urgency_text: string;
  scarcity_count: number;
  cta_text: string;
  cta_subtext: string;
  terms: string;
  is_active: boolean;
  // Public landing page fields
  is_public: boolean;
  public_slug: string;
  require_email: boolean;
  require_phone: boolean;
  require_name: boolean;
}

const initialFormData: FormData = {
  name: "",
  description: "",
  headline: "",
  subheadline: "",
  discount_type: "percentage",
  discount_value: 0,
  regular_price: 0,
  offer_price: 0,
  savings_amount: 0,
  value_stack_items: [],
  lead_magnet_ids: [],
  guarantee_type: "",
  guarantee_days: 30,
  guarantee_text: "",
  urgency_type: "",
  urgency_text: "",
  scarcity_count: 0,
  cta_text: "Get Started Now",
  cta_subtext: "",
  terms: "",
  is_active: true,
  // Public landing page defaults
  is_public: false,
  public_slug: "",
  require_email: true,
  require_phone: false,
  require_name: false,
};

export function OfferBuilderWizard({
  workspaceId,
  existingOffer,
  onSuccess,
}: OfferBuilderWizardProps) {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [currentStep, setCurrentStep] = useState(0);
  const [formData, setFormData] = useState<FormData>(() => {
    if (existingOffer) {
      return {
        ...initialFormData,
        name: existingOffer.name,
        description: existingOffer.description || "",
        headline: existingOffer.headline || "",
        subheadline: existingOffer.subheadline || "",
        discount_type: existingOffer.discount_type,
        discount_value: existingOffer.discount_value,
        regular_price: existingOffer.regular_price || 0,
        offer_price: existingOffer.offer_price || 0,
        savings_amount: existingOffer.savings_amount || 0,
        value_stack_items: existingOffer.value_stack_items || [],
        lead_magnet_ids: existingOffer.lead_magnets?.map((lm) => lm.id) || [],
        guarantee_type: existingOffer.guarantee_type || "",
        guarantee_days: existingOffer.guarantee_days || 30,
        guarantee_text: existingOffer.guarantee_text || "",
        urgency_type: existingOffer.urgency_type || "",
        urgency_text: existingOffer.urgency_text || "",
        scarcity_count: existingOffer.scarcity_count || 0,
        cta_text: existingOffer.cta_text || "Get Started Now",
        cta_subtext: existingOffer.cta_subtext || "",
        terms: existingOffer.terms || "",
        is_active: existingOffer.is_active,
        // Public landing page fields
        is_public: existingOffer.is_public || false,
        public_slug: existingOffer.public_slug || "",
        require_email: existingOffer.require_email ?? true,
        require_phone: existingOffer.require_phone || false,
        require_name: existingOffer.require_name || false,
      };
    }
    return initialFormData;
  });

  // Fetch lead magnets
  const { data: leadMagnetsData } = useQuery({
    queryKey: ["lead-magnets", workspaceId],
    queryFn: () => leadMagnetsApi.list(workspaceId, { active_only: true }),
  });

  const leadMagnets = leadMagnetsData?.items || [];
  const selectedLeadMagnets = leadMagnets.filter((lm) =>
    formData.lead_magnet_ids.includes(lm.id)
  );

  // Create/update mutation
  const createMutation = useMutation({
    mutationFn: async (data: CreateOfferRequest) => {
      const offer = existingOffer
        ? await offersApi.update(workspaceId, existingOffer.id, data)
        : await offersApi.create(workspaceId, data);

      // Attach lead magnets if any
      if (formData.lead_magnet_ids.length > 0) {
        await offersApi.attachLeadMagnets(
          workspaceId,
          offer.id,
          formData.lead_magnet_ids
        );
      }

      return offer;
    },
    onSuccess: (offer) => {
      queryClient.invalidateQueries({ queryKey: ["offers", workspaceId] });
      if (onSuccess) {
        onSuccess(offer);
      } else {
        router.push(`/offers`);
      }
    },
  });

  // Create lead magnet mutation
  const createLeadMagnetMutation = useMutation({
    mutationFn: (data: Partial<LeadMagnet>) =>
      leadMagnetsApi.create(workspaceId, {
        name: data.name || "",
        magnet_type: data.magnet_type || "pdf",
        delivery_method: data.delivery_method || "email",
        content_url: data.content_url || "",
        description: data.description,
        estimated_value: data.estimated_value,
        is_active: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["lead-magnets", workspaceId] });
    },
  });

  const updateFormData = useCallback(
    (updates: Partial<FormData>) => {
      setFormData((prev) => ({ ...prev, ...updates }));
    },
    []
  );

  const goNext = () => {
    if (currentStep < STEPS.length - 1) {
      setCurrentStep(currentStep + 1);
    }
  };

  const goPrev = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleSubmit = () => {
    const offerData: CreateOfferRequest = {
      name: formData.name,
      description: formData.description || undefined,
      discount_type: formData.discount_type,
      discount_value: formData.discount_value,
      terms: formData.terms || undefined,
      is_active: formData.is_active,
      headline: formData.headline || undefined,
      subheadline: formData.subheadline || undefined,
      regular_price: formData.regular_price || undefined,
      offer_price: formData.offer_price || undefined,
      savings_amount: formData.savings_amount || undefined,
      guarantee_type: formData.guarantee_type || undefined,
      guarantee_days: formData.guarantee_days || undefined,
      guarantee_text: formData.guarantee_text || undefined,
      urgency_type: formData.urgency_type || undefined,
      urgency_text: formData.urgency_text || undefined,
      scarcity_count: formData.scarcity_count || undefined,
      value_stack_items: formData.value_stack_items.length > 0
        ? formData.value_stack_items
        : undefined,
      cta_text: formData.cta_text || undefined,
      cta_subtext: formData.cta_subtext || undefined,
      // Public landing page fields
      is_public: formData.is_public,
      public_slug: formData.public_slug || undefined,
      require_email: formData.require_email,
      require_phone: formData.require_phone,
      require_name: formData.require_name,
    };

    createMutation.mutate(offerData);
  };

  const renderStepContent = () => {
    switch (STEPS[currentStep].id) {
      case "basics":
        return (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <h4 className="font-medium">Basic Information</h4>
                <p className="text-sm text-muted-foreground">
                  Define your offer or generate content with AI
                </p>
              </div>
              <AIOfferWriter
                workspaceId={workspaceId}
                onApply={(data) => {
                  updateFormData({
                    headline: data.headline ?? formData.headline,
                    subheadline: data.subheadline ?? formData.subheadline,
                    value_stack_items: data.value_stack_items ?? formData.value_stack_items,
                    guarantee_type: data.guarantee_type ?? formData.guarantee_type,
                    guarantee_days: data.guarantee_days ?? formData.guarantee_days,
                    guarantee_text: data.guarantee_text ?? formData.guarantee_text,
                    urgency_type: data.urgency_type ?? formData.urgency_type,
                    urgency_text: data.urgency_text ?? formData.urgency_text,
                    scarcity_count: data.scarcity_count ?? formData.scarcity_count,
                    cta_text: data.cta_text ?? formData.cta_text,
                    cta_subtext: data.cta_subtext ?? formData.cta_subtext,
                  });
                }}
              />
            </div>

            <Separator />

            <div className="space-y-2">
              <Label htmlFor="name">Offer Name *</Label>
              <Input
                id="name"
                placeholder="e.g., Ultimate Growth Package"
                value={formData.name}
                onChange={(e) => updateFormData({ name: e.target.value })}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="headline">Headline</Label>
              <Input
                id="headline"
                placeholder="e.g., Get 10X Results Without 10X The Work"
                value={formData.headline}
                onChange={(e) => updateFormData({ headline: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">
                A compelling headline that grabs attention
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="subheadline">Subheadline</Label>
              <Textarea
                id="subheadline"
                placeholder="Supporting text that expands on your headline..."
                value={formData.subheadline}
                onChange={(e) => updateFormData({ subheadline: e.target.value })}
                rows={2}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                placeholder="Detailed description of what's included..."
                value={formData.description}
                onChange={(e) => updateFormData({ description: e.target.value })}
                rows={3}
              />
            </div>
          </div>
        );

      case "pricing":
        return (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Discount Type</Label>
                <Select
                  value={formData.discount_type}
                  onValueChange={(v) =>
                    updateFormData({ discount_type: v as DiscountType })
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="percentage">Percentage Off</SelectItem>
                    <SelectItem value="fixed">Fixed Amount Off</SelectItem>
                    <SelectItem value="free_service">Free Service</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="discount_value">
                  {formData.discount_type === "percentage"
                    ? "Discount %"
                    : "Discount Amount ($)"}
                </Label>
                <Input
                  id="discount_value"
                  type="number"
                  min="0"
                  value={formData.discount_value || ""}
                  onChange={(e) =>
                    updateFormData({
                      discount_value: parseFloat(e.target.value) || 0,
                    })
                  }
                  disabled={formData.discount_type === "free_service"}
                />
              </div>
            </div>

            <Separator />

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="regular_price">Regular Price ($)</Label>
                <Input
                  id="regular_price"
                  type="number"
                  min="0"
                  placeholder="e.g., 997"
                  value={formData.regular_price || ""}
                  onChange={(e) =>
                    updateFormData({
                      regular_price: parseFloat(e.target.value) || 0,
                    })
                  }
                />
                <p className="text-xs text-muted-foreground">
                  Anchor price (crossed out)
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="offer_price">Your Price ($)</Label>
                <Input
                  id="offer_price"
                  type="number"
                  min="0"
                  placeholder="e.g., 497"
                  value={formData.offer_price || ""}
                  onChange={(e) =>
                    updateFormData({
                      offer_price: parseFloat(e.target.value) || 0,
                    })
                  }
                />
                <p className="text-xs text-muted-foreground">
                  What they actually pay
                </p>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="savings">Savings Amount ($)</Label>
              <Input
                id="savings"
                type="number"
                min="0"
                placeholder="Auto-calculated or custom"
                value={
                  formData.savings_amount ||
                  (formData.regular_price > 0 && formData.offer_price > 0
                    ? formData.regular_price - formData.offer_price
                    : "")
                }
                onChange={(e) =>
                  updateFormData({
                    savings_amount: parseFloat(e.target.value) || 0,
                  })
                }
              />
            </div>
          </div>
        );

      case "value-stack":
        return (
          <ValueStackBuilder
            items={formData.value_stack_items}
            onChange={(items) => updateFormData({ value_stack_items: items })}
          />
        );

      case "lead-magnets":
        return (
          <LeadMagnetSelector
            leadMagnets={leadMagnets}
            selectedIds={formData.lead_magnet_ids}
            onSelect={(ids) => updateFormData({ lead_magnet_ids: ids })}
            onCreateLeadMagnet={async (lm) => {
              await createLeadMagnetMutation.mutateAsync(lm);
            }}
            multiSelect
          />
        );

      case "guarantee":
        return (
          <div className="space-y-6">
            <div className="space-y-2">
              <Label>Guarantee Type</Label>
              <Select
                value={formData.guarantee_type}
                onValueChange={(v) =>
                  updateFormData({ guarantee_type: v as GuaranteeType })
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select a guarantee type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="money_back">Money-Back Guarantee</SelectItem>
                  <SelectItem value="satisfaction">
                    Satisfaction Guarantee
                  </SelectItem>
                  <SelectItem value="results">Results Guarantee</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {formData.guarantee_type && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="guarantee_days">Guarantee Period (Days)</Label>
                  <Input
                    id="guarantee_days"
                    type="number"
                    min="0"
                    value={formData.guarantee_days || ""}
                    onChange={(e) =>
                      updateFormData({
                        guarantee_days: parseInt(e.target.value) || 0,
                      })
                    }
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="guarantee_text">Custom Guarantee Text</Label>
                  <Textarea
                    id="guarantee_text"
                    placeholder="e.g., If you don't see results in 30 days, we'll refund every penny..."
                    value={formData.guarantee_text}
                    onChange={(e) =>
                      updateFormData({ guarantee_text: e.target.value })
                    }
                    rows={3}
                  />
                </div>
              </>
            )}
          </div>
        );

      case "urgency":
        return (
          <div className="space-y-6">
            <div className="space-y-2">
              <Label>Urgency Type</Label>
              <Select
                value={formData.urgency_type}
                onValueChange={(v) =>
                  updateFormData({ urgency_type: v as UrgencyType })
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select urgency type (optional)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="limited_time">Limited Time Offer</SelectItem>
                  <SelectItem value="limited_quantity">
                    Limited Quantity
                  </SelectItem>
                  <SelectItem value="expiring">Expiring Soon</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {formData.urgency_type && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="urgency_text">Urgency Message</Label>
                  <Input
                    id="urgency_text"
                    placeholder="e.g., Offer ends Friday at midnight!"
                    value={formData.urgency_text}
                    onChange={(e) =>
                      updateFormData({ urgency_text: e.target.value })
                    }
                  />
                </div>

                {formData.urgency_type === "limited_quantity" && (
                  <div className="space-y-2">
                    <Label htmlFor="scarcity_count">Spots Available</Label>
                    <Input
                      id="scarcity_count"
                      type="number"
                      min="0"
                      placeholder="e.g., 10"
                      value={formData.scarcity_count || ""}
                      onChange={(e) =>
                        updateFormData({
                          scarcity_count: parseInt(e.target.value) || 0,
                        })
                      }
                    />
                  </div>
                )}
              </>
            )}

            <Separator />

            <div className="space-y-2">
              <Label htmlFor="cta_text">Call to Action Button Text</Label>
              <Input
                id="cta_text"
                placeholder="e.g., Get Started Now"
                value={formData.cta_text}
                onChange={(e) => updateFormData({ cta_text: e.target.value })}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="cta_subtext">CTA Subtext</Label>
              <Input
                id="cta_subtext"
                placeholder="e.g., Risk-free • Cancel anytime"
                value={formData.cta_subtext}
                onChange={(e) => updateFormData({ cta_subtext: e.target.value })}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="terms">Terms & Conditions</Label>
              <Textarea
                id="terms"
                placeholder="Any terms, restrictions, or fine print..."
                value={formData.terms}
                onChange={(e) => updateFormData({ terms: e.target.value })}
                rows={2}
              />
            </div>
          </div>
        );

      case "publish":
        return (
          <div className="space-y-6">
            <div className="flex items-center justify-between p-4 border rounded-lg">
              <div className="space-y-0.5">
                <Label className="text-base">Public Landing Page</Label>
                <p className="text-sm text-muted-foreground">
                  Enable a shareable landing page for this offer
                </p>
              </div>
              <Switch
                checked={formData.is_public}
                onCheckedChange={(checked) =>
                  updateFormData({ is_public: checked })
                }
              />
            </div>

            {formData.is_public && (
              <>
                <div className="space-y-2">
                  <Label htmlFor="public_slug">URL Slug</Label>
                  <div className="flex gap-2">
                    <div className="flex-1 flex items-center gap-2 p-2 bg-muted rounded-md text-sm text-muted-foreground">
                      <span>{typeof window !== "undefined" ? window.location.origin : ""}/p/offers/</span>
                      <Input
                        id="public_slug"
                        placeholder="my-offer"
                        value={formData.public_slug}
                        onChange={(e) =>
                          updateFormData({
                            public_slug: e.target.value
                              .toLowerCase()
                              .replace(/[^a-z0-9-]/g, "-")
                              .replace(/-+/g, "-"),
                          })
                        }
                        className="flex-1 h-8"
                      />
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Only lowercase letters, numbers, and dashes allowed
                  </p>
                </div>

                {formData.public_slug && (
                  <div className="flex items-center gap-2 p-3 bg-primary/5 rounded-lg border border-primary/20">
                    <Globe className="size-4 text-primary" />
                    <span className="text-sm flex-1 truncate">
                      {typeof window !== "undefined" ? window.location.origin : ""}/p/offers/{formData.public_slug}
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        const url = `${window.location.origin}/p/offers/${formData.public_slug}`;
                        navigator.clipboard.writeText(url);
                      }}
                    >
                      <Copy className="size-4" />
                    </Button>
                    {existingOffer?.is_public && existingOffer?.public_slug && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          window.open(
                            `/p/offers/${existingOffer.public_slug}`,
                            "_blank"
                          )
                        }
                      >
                        <ExternalLink className="size-4" />
                      </Button>
                    )}
                  </div>
                )}

                <Separator />

                <div className="space-y-4">
                  <h4 className="font-medium">Required Fields</h4>
                  <p className="text-sm text-muted-foreground">
                    Choose what information visitors must provide to access this offer
                  </p>

                  <div className="space-y-3">
                    <div className="flex items-center space-x-3">
                      <Checkbox
                        id="require_email"
                        checked={formData.require_email}
                        onCheckedChange={(checked) =>
                          updateFormData({ require_email: checked === true })
                        }
                      />
                      <Label
                        htmlFor="require_email"
                        className="text-sm font-normal cursor-pointer"
                      >
                        Email address (recommended)
                      </Label>
                    </div>

                    <div className="flex items-center space-x-3">
                      <Checkbox
                        id="require_phone"
                        checked={formData.require_phone}
                        onCheckedChange={(checked) =>
                          updateFormData({ require_phone: checked === true })
                        }
                      />
                      <Label
                        htmlFor="require_phone"
                        className="text-sm font-normal cursor-pointer"
                      >
                        Phone number
                      </Label>
                    </div>

                    <div className="flex items-center space-x-3">
                      <Checkbox
                        id="require_name"
                        checked={formData.require_name}
                        onCheckedChange={(checked) =>
                          updateFormData({ require_name: checked === true })
                        }
                      />
                      <Label
                        htmlFor="require_name"
                        className="text-sm font-normal cursor-pointer"
                      >
                        Full name
                      </Label>
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        );

      case "review":
        return (
          <div className="space-y-6">
            <div className="text-center mb-6">
              <h3 className="text-lg font-semibold">Review Your Offer</h3>
              <p className="text-muted-foreground">
                Here&apos;s how your offer will appear
              </p>
            </div>
            <OfferPreview offer={formData} leadMagnets={selectedLeadMagnets} />
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="space-y-6">
      {/* Step Indicator */}
      <div className="flex items-center justify-between mb-8">
        {STEPS.map((step, index) => (
          <div
            key={step.id}
            className={`flex items-center ${
              index < STEPS.length - 1 ? "flex-1" : ""
            }`}
          >
            <button
              type="button"
              onClick={() => setCurrentStep(index)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-colors ${
                index === currentStep
                  ? "bg-primary text-primary-foreground"
                  : index < currentStep
                  ? "bg-primary/20 text-primary"
                  : "bg-muted text-muted-foreground"
              }`}
            >
              {index < currentStep ? (
                <Check className="size-4" />
              ) : (
                step.icon
              )}
              <span className="hidden sm:inline text-sm font-medium">
                {step.label}
              </span>
            </button>
            {index < STEPS.length - 1 && (
              <div
                className={`flex-1 h-0.5 mx-2 ${
                  index < currentStep ? "bg-primary" : "bg-muted"
                }`}
              />
            )}
          </div>
        ))}
      </div>

      {/* Step Content */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {STEPS[currentStep].icon}
            {STEPS[currentStep].label}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <AnimatePresence mode="wait">
            <motion.div
              key={currentStep}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2 }}
            >
              {renderStepContent()}
            </motion.div>
          </AnimatePresence>
        </CardContent>
      </Card>

      {/* Navigation */}
      <div className="flex items-center justify-between">
        <Button
          variant="outline"
          onClick={goPrev}
          disabled={currentStep === 0}
        >
          <ChevronLeft className="size-4 mr-1" />
          Previous
        </Button>

        {currentStep < STEPS.length - 1 ? (
          <Button onClick={goNext} disabled={!formData.name}>
            Next
            <ChevronRight className="size-4 ml-1" />
          </Button>
        ) : (
          <Button
            onClick={handleSubmit}
            disabled={!formData.name || createMutation.isPending}
          >
            {createMutation.isPending ? (
              <>
                <Loader2 className="size-4 mr-2 animate-spin" />
                Creating...
              </>
            ) : (
              <>
                <Check className="size-4 mr-2" />
                {existingOffer ? "Update Offer" : "Create Offer"}
              </>
            )}
          </Button>
        )}
      </div>
    </div>
  );
}
