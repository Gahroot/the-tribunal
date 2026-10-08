"use client";

import { useQuery, useMutation } from "@tanstack/react-query";
import { LeadMagnetContent } from "@tribunal/lead-capture";
import {
  Check,
  Shield,
  Clock,
  Gift,
  Loader2,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import { useState, use } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageErrorState, PageLoadingState } from "@/components/ui/page-state";
import { Separator } from "@/components/ui/separator";
import { publicOffersApi, type OptInRequest, type OptInResponse } from "@/lib/api/public-offers";
import { queryKeys } from "@/lib/query-keys";
import { getApiErrorMessage } from "@/lib/utils/errors";
import { formatNumber } from "@/lib/utils/number";

interface PublicOfferPageProps {
  params: Promise<{ slug: string }>;
}

export default function PublicOfferPage({ params }: PublicOfferPageProps) {
  const { slug } = use(params);

  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [optInResult, setOptInResult] = useState<OptInResponse | null>(null);

  const { data: offer, isPending, error } = useQuery({
    queryKey: queryKeys.publicOffers.bySlug(slug),
    queryFn: () => publicOffersApi.get(slug),
    enabled: !!slug,
    retry: false,
  });

  const optInMutation = useMutation({
    mutationFn: (data: OptInRequest) => publicOffersApi.optIn(slug, data),
    onSuccess: (result) => {
      if (result.success) setOptInResult(result);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    optInMutation.mutate({
      email: email || undefined,
      phone_number: phone || undefined,
      name: name || undefined,
    });
  };

  const isFormValid = () => {
    if (offer?.require_email && !email) return false;
    if (offer?.require_phone && !phone) return false;
    if (offer?.require_name && !name.trim()) return false;
    // A lead must leave a way to reach them; a name alone is rejected server-side.
    return Boolean(email.trim() || phone.trim());
  };

  if (isPending) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-background to-muted">
        <PageLoadingState className="min-h-screen" />
      </div>
    );
  }

  if (error || !offer) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-background to-muted">
        <PageErrorState
          className="min-h-screen"
          message="This offer may have expired or the link is incorrect."
        />
      </div>
    );
  }

  if (optInResult) {
    const deliveries = optInResult.deliveries ?? [];
    const accepted = deliveries.filter((delivery) => delivery.status === "accepted").length;
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-background to-muted p-4">
        <Card className="max-w-md w-full">
          <CardContent className="pt-6 text-center">
            <CheckCircle2 className="size-16 text-success mx-auto mb-4" />
            <h1 className="text-2xl font-bold mb-2">You&apos;re In!</h1>
            <p className="text-muted-foreground mb-4" role="status">
              Your signup is saved.
              {accepted > 0 && ` ${accepted} of ${deliveries.length} bonus emails accepted by the email provider. This does not confirm inbox receipt; check your inbox and spam folder.`}
              {deliveries.length > accepted && " Email acceptance could not be confirmed for some bonuses. You do not need to sign up again."}
            </p>
            {deliveries.map((delivery) => {
              const magnet = offer.lead_magnets.find((item) => item.id === delivery.lead_magnet_id);
              const labels = {
                accepted: "Email accepted by provider; inbox receipt not confirmed.",
                failed: "Email acceptance could not be confirmed.",
                unavailable: "Email delivery is currently unavailable.",
                missing_email: "Email could not be sent because no email address was provided.",
                pending: "Email acceptance has not been confirmed.",
              };
              return <p key={delivery.lead_magnet_id} className="text-sm text-muted-foreground mb-2">
                {magnet?.name ?? "Bonus"}: {labels[delivery.status]}
              </p>;
            })}
            {offer.lead_magnets.length > 0 && <>
              <p className="text-sm text-muted-foreground mb-4">Access available bonuses below without another signup. If a bonus is unavailable, contact the business that shared this offer.</p>
              {offer.lead_magnets.map((magnet) => (
                <div key={magnet.id} className="text-left space-y-2 mb-4">
                  <h3 className="font-semibold">{magnet.name}</h3>
                  {magnet.content_url || magnet.content_data
                    ? <LeadMagnetContent magnet={magnet} />
                    : <p className="text-sm text-muted-foreground">This bonus is currently unavailable. Contact the business that shared this offer.</p>}
                </div>
              ))}
            </>}
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-background to-muted">
      <div className="container max-w-4xl py-8 px-4">
        {/* Hero Section */}
        <div className="text-center mb-8">
          {offer.headline && (
            <h1 className="text-3xl md:text-4xl font-bold mb-4 leading-tight">
              {offer.headline}
            </h1>
          )}
          {offer.subheadline && (
            <p className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto">
              {offer.subheadline}
            </p>
          )}
        </div>

        <div className="grid gap-8 lg:grid-cols-5">
          {/* Left Column - Value Stack & Bonuses */}
          <div className="min-w-0 lg:col-span-3 space-y-6">
            {/* Value Stack */}
            {offer.value_stack_items && offer.value_stack_items.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Here&apos;s Everything You Get</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {offer.value_stack_items.map((item, index) => (
                    <div
                      key={index}
                      className="flex items-start gap-3 p-3 rounded-lg bg-muted/50"
                    >
                      <Check className="size-5 text-success mt-0.5 flex-shrink-0" />
                      <div className="flex-1">
                        <div className="flex items-center justify-between">
                          <span className="font-medium">{item.name}</span>
                          {item.value > 0 && (
                            <span className="text-sm text-muted-foreground">
                              ${formatNumber(item.value)} value
                            </span>
                          )}
                        </div>
                        {item.description && (
                          <p className="text-sm text-muted-foreground mt-1">
                            {item.description}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            {/* Bonuses (Lead Magnets) */}
            {offer.lead_magnets.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Gift className="size-5 text-primary" />
                    Exclusive Bonuses
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {offer.lead_magnets.map((lm) => (
                    <div
                      key={lm.id}
                      className="flex items-start gap-3 p-3 rounded-lg border bg-background"
                    >
                      <Gift className="size-5 text-primary mt-0.5 flex-shrink-0" />
                      <div className="min-w-0 flex-1 space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="font-medium">{lm.name}</span>
                          {lm.estimated_value && (
                            <Badge variant="secondary">
                              ${formatNumber(lm.estimated_value)} value
                            </Badge>
                          )}
                        </div>
                        {lm.description && (
                          <p className="text-sm text-muted-foreground">
                            {lm.description}
                          </p>
                        )}
                        <LeadMagnetContent magnet={lm} />
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            {/* Guarantee */}
            {offer.guarantee_type && (
              <Card className="border">
                <CardContent className="pt-6">
                  <div className="flex items-start gap-4">
                    <div className="p-3 rounded-full">
                      <Shield className="size-6 text-success" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-lg mb-1">
                        {offer.guarantee_days}-Day{" "}
                        {offer.guarantee_type === "money_back"
                          ? "Money-Back"
                          : offer.guarantee_type === "satisfaction"
                          ? "Satisfaction"
                          : "Results"}{" "}
                        Guarantee
                      </h3>
                      {offer.guarantee_text && (
                        <p className="text-muted-foreground">
                          {offer.guarantee_text}
                        </p>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Right Column - Pricing & Form */}
          <div className="lg:col-span-2 space-y-6">
            {/* Pricing Card */}
            <Card className="sticky top-4">
              <CardHeader className="text-center pb-2">
                {offer.total_value && (
                  <p className="text-sm text-muted-foreground mb-1">
                    Total Value: ${formatNumber(offer.total_value)}
                  </p>
                )}
                {offer.offer_price != null && (
                  <div className="flex items-center justify-center gap-3 mb-2">
                    {offer.regular_price != null && offer.regular_price > offer.offer_price && (
                      <span className="text-2xl text-muted-foreground line-through">
                        ${formatNumber(offer.regular_price)}
                      </span>
                    )}
                    <span className="text-4xl font-bold text-primary">
                      ${formatNumber(offer.offer_price)}
                    </span>
                  </div>
                )}
                {offer.savings_amount && offer.savings_amount > 0 && (
                  <Badge variant="secondary" className="text-primary">
                    Save ${formatNumber(offer.savings_amount)}
                  </Badge>
                )}
              </CardHeader>

              <CardContent className="space-y-4">
                <Separator />

                {/* Opt-in Form */}
                <form onSubmit={handleSubmit} className="space-y-4">
                  {(offer.require_name || (!offer.require_email && !offer.require_phone)) && (
                    <div className="space-y-2">
                      <Label htmlFor="name">
                        Name {offer.require_name && "*"}
                      </Label>
                      <Input
                        id="name"
                        placeholder="Your name"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        required={offer.require_name}
                      />
                    </div>
                  )}

                  <div className="space-y-2">
                    <Label htmlFor="email">
                      Email {offer.require_email && "*"}
                    </Label>
                    <Input
                      id="email"
                      type="email"
                      placeholder="you@example.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required={offer.require_email}
                    />
                  </div>

                  {offer.require_phone && (
                    <div className="space-y-2">
                      <Label htmlFor="phone">Phone *</Label>
                      <Input
                        id="phone"
                        type="tel"
                        placeholder="+1 (555) 123-4567"
                        value={phone}
                        onChange={(e) => setPhone(e.target.value)}
                        required
                      />
                    </div>
                  )}

                  {optInMutation.isError && (
                    <Alert variant="destructive">
                      <AlertCircle className="size-4" />
                      <AlertTitle>Error</AlertTitle>
                      <AlertDescription>
                        {getApiErrorMessage(
                          optInMutation.error,
                          "Something went wrong. Please try again."
                        )}
                      </AlertDescription>
                    </Alert>
                  )}

                  <Button
                    type="submit"
                    size="lg"
                    className="w-full text-lg py-6"
                    disabled={!isFormValid() || optInMutation.isPending}
                  >
                    {optInMutation.isPending ? (
                      <>
                        <Loader2 className="size-5 mr-2 animate-spin" />
                        Processing...
                      </>
                    ) : (
                      offer.cta_text || "Get Access Now"
                    )}
                  </Button>

                  {offer.cta_subtext && (
                    <p className="text-center text-sm text-muted-foreground">
                      {offer.cta_subtext}
                    </p>
                  )}
                </form>
              </CardContent>
            </Card>

            {/* Urgency Banner */}
            {offer.urgency_type && offer.urgency_text && (
              <Alert className="border bg-background text-foreground">
                <Clock className="size-4 text-warning" />
                <AlertDescription className="font-medium">
                  {offer.urgency_text}
                  {offer.scarcity_count && offer.scarcity_count > 0 && (
                    <span className="block mt-1">
                      Only {offer.scarcity_count} spots remaining!
                    </span>
                  )}
                </AlertDescription>
              </Alert>
            )}
          </div>
        </div>

        {/* Description */}
        {offer.description && (
          <Card className="mt-8">
            <CardContent className="pt-6 prose dark:prose-invert max-w-none">
              <p className="text-muted-foreground whitespace-pre-wrap">
                {offer.description}
              </p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
