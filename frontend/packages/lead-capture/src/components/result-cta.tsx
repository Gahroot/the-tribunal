"use client";

import { useId } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ResultCTADestination } from "@/types";

export interface ResultCTAContext {
  onBooking?: () => void;
  onOffer?: () => void;
}

// Only explicit web destinations; never scripts, credentials or ambiguous paths.
function safeDestination(value: unknown): string | undefined {
  if (typeof value !== "string" || /[\s\u0000-\u001f\u007f\\]/u.test(value)) return;
  try {
    const url = new URL(value);
    if (
      /^https?:\/\/[^/]/i.test(value) &&
      ["http:", "https:"].includes(url.protocol) &&
      !url.username &&
      !url.password
    )
      return value;
  } catch {
    // Permit only the existing public offer route, not arbitrary internal pages.
    if (/^\/p\/offers\/[a-zA-Z0-9_-]+$/.test(value)) return value;
  }
}

export function ResultCTA({
  text,
  destination,
  onBooking,
  onOffer,
}: ResultCTAContext & {
  text: string;
  destination: ResultCTADestination;
}) {
  const id = useId();
  if (!text.trim()) return null;
  const action = destination.cta_action ?? "link";
  const supported = ["link", "booking", "offer"].includes(action);
  const href = supported ? safeDestination(destination.cta_url) : undefined;
  // A present but invalid URL must not silently fall back to another action.
  const callback =
    !destination.cta_url &&
    (action === "booking" ? onBooking : action === "offer" ? onOffer : undefined);
  if (href)
    return (
      <Button asChild size="sm">
        <a href={href} rel="noopener noreferrer">
          {text}
        </a>
      </Button>
    );
  if (callback)
    return (
      <Button size="sm" type="button" onClick={callback}>
        {text}
      </Button>
    );
  return (
    <div className="space-y-1">
      <Button size="sm" type="button" disabled aria-describedby={id}>
        {text}
      </Button>
      <p id={id} className="text-xs text-muted-foreground">
        This next step is currently unavailable. Contact the business that shared this result.
      </p>
    </div>
  );
}

export function ResultCTAEditor({
  destination,
  onChange,
}: {
  destination: ResultCTADestination;
  onChange: (updates: ResultCTADestination) => void;
}) {
  const id = useId();
  const valid = safeDestination(destination.cta_url);
  return (
    <div className="space-y-2">
      <Label htmlFor={`${id}-action`}>CTA action</Label>
      <select
        id={`${id}-action`}
        className="w-full rounded-md border bg-background p-2 text-sm"
        value={destination.cta_action ?? "link"}
        onChange={(event) =>
          onChange({ cta_action: event.target.value as ResultCTADestination["cta_action"] })
        }
      >
        <option value="link">Open link</option>
        <option value="booking">Booking</option>
        <option value="offer">Offer signup</option>
      </select>
      <Label htmlFor={`${id}-url`}>CTA destination URL</Label>
      <Input
        id={`${id}-url`}
        value={destination.cta_url ?? ""}
        placeholder="https://… or /p/offers/public-slug"
        aria-describedby={`${id}-help`}
        onChange={(event) => onChange({ cta_url: event.target.value })}
      />
      <p id={`${id}-help`} className="text-xs text-muted-foreground">
        {destination.cta_url && !valid
          ? "Enter a valid HTTP(S) URL or /p/offers/public-slug. Unsafe destinations are disabled."
          : !valid
            ? "Configure a destination to enable this CTA. Offer signup can use the hosting offer’s existing form; booking requires a configured booking link or host callback. Without a host action, preview and public CTAs remain disabled."
            : "Use an existing booking link or public offer URL. This CTA does not create a booking or payment."}
      </p>
    </div>
  );
}
