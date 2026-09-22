"use client";

import Image from "next/image";

import type { Offer } from "@/types";

import type { CampaignMedia } from "./campaign-media-upload";

interface PhonePreviewProps {
  senderLabel: string;
  message: string;
  media?: CampaignMedia | null;
  offer?: Offer | null;
  followUpEnabled?: boolean;
  followUpDelayHours?: number;
  followUpMessage?: string;
}

function formatOfferDiscount(offer?: Offer | null): string {
  if (!offer) return "20% off";
  switch (offer.discount_type) {
    case "percentage":
      return `${offer.discount_value}% off`;
    case "fixed":
      return `$${offer.discount_value} off`;
    case "free_service":
      return "Free";
    default:
      return "20% off";
  }
}

function withSampleValues(text: string, offer?: Offer | null): string {
  return text
    .replace(/\{first_name\}/gi, "Jordan")
    .replace(/\{last_name\}/gi, "Reyes")
    .replace(/\{company_name\}/gi, "Brightside Realty")
    .replace(/\{offer_name\}/gi, offer?.name ?? "Summer Special")
    .replace(/\{offer_discount\}/gi, formatOfferDiscount(offer))
    .replace(/\{offer_terms\}/gi, offer?.terms || "New customers only");
}

function segmentCount(text: string): number {
  if (!text.trim()) return 1;
  return Math.max(1, Math.ceil(text.length / 160));
}

function MessageBubble({ text, offer }: { text: string; offer?: Offer | null }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-sm bg-primary px-3.5 py-2.5 text-sm text-primary-foreground">
        {withSampleValues(text, offer)}
      </div>
    </div>
  );
}

/**
 * Live phone-style preview of the outbound message thread, rendered with
 * sample contact data so operators see what recipients will receive.
 */
export function PhonePreview({
  senderLabel,
  message,
  media,
  offer,
  followUpEnabled = false,
  followUpDelayHours = 24,
  followUpMessage = "",
}: PhonePreviewProps) {
  return (
    <div className="overflow-hidden rounded-3xl border bg-background shadow-sm">
      <div className="flex items-center gap-3 border-b px-4 py-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium">
          JR
        </div>
        <div className="min-w-0 leading-tight">
          <p className="truncate text-sm font-medium">Jordan Reyes</p>
          <p className="truncate text-xs text-muted-foreground">{senderLabel}</p>
        </div>
      </div>

      <div className="min-h-[260px] space-y-3 bg-muted/30 px-4 py-4">
        {media && (
          <div className="flex justify-end">
            <div className="max-w-[85%] overflow-hidden rounded-2xl border bg-background">
              <Image
                src={media.dataUrl}
                alt={media.name}
                width={240}
                height={160}
                unoptimized
                className="h-40 w-60 object-cover"
              />
            </div>
          </div>
        )}

        {message.trim() ? (
          <>
            <MessageBubble text={message} offer={offer} />
            <p className="text-right text-[11px] text-muted-foreground">
              {message.length} characters · {segmentCount(message)} segment
              {segmentCount(message) === 1 ? "" : "s"}
            </p>
          </>
        ) : (
          <p className="py-12 text-center text-sm text-muted-foreground">
            Your message will appear here
          </p>
        )}

        {followUpEnabled && followUpMessage.trim() && (
          <>
            <div className="flex items-center gap-2">
              <div className="h-px flex-1 bg-border" />
              <span className="text-[11px] text-muted-foreground">
                Follow-up after {followUpDelayHours}h
              </span>
              <div className="h-px flex-1 bg-border" />
            </div>
            <MessageBubble text={followUpMessage} offer={offer} />
          </>
        )}
      </div>

      <div className="border-t px-4 py-3 text-center text-[11px] text-muted-foreground">
        Preview uses sample contact data
      </div>
    </div>
  );
}
