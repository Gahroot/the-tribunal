"use client";

import { useMemo } from "react";

import { Label } from "@/components/ui/label";
import { getModePath, type EmbedFormValues } from "./embed-types";

interface EmbedPreviewProps {
  values: EmbedFormValues;
  baseUrl: string;
  publicId: string;
}

/**
 * Live iframe preview for the embed-agent dialog.
 *
 * Kept as a default export so it can be `next/dynamic`-imported by the dialog
 * — the iframe + its mounted child route are roughly ~80KB of JS that we
 * don't want to ship until the user actually opens the embed dialog.
 */
export default function EmbedPreview({
  values,
  baseUrl,
  publicId,
}: EmbedPreviewProps) {
  const modePath = useMemo(
    () => getModePath(values.display, values.mode),
    [values.display, values.mode],
  );

  const previewUrl = useMemo(() => {
    const path = modePath
      ? `/embed/${publicId}/${modePath}`
      : `/embed/${publicId}`;
    return `${path}?theme=${values.theme}&preview=true`;
  }, [publicId, modePath, values.theme]);

  // Reload the iframe whenever any visible setting changes.
  const previewKey = `${values.theme}-${values.mode}-${values.primaryColor}-${values.display}`;

  return (
    <div className="min-w-0 space-y-2 lg:w-[45%]">
      <Label className="text-sm font-medium text-muted-foreground">
        Live Preview
      </Label>
      {publicId ? (
        <div className="overflow-hidden rounded-xl border">
          <iframe
            key={previewKey}
            src={`${baseUrl}${previewUrl}`}
            width="100%"
            height="400px"
            className="block rounded-xl"
            style={{ border: "none" }}
            allow="microphone"
            title="Embed preview"
          />
        </div>
      ) : (
        <div className="flex h-[400px] items-center justify-center rounded-xl border bg-muted text-sm text-muted-foreground">
          Save settings to generate a preview
        </div>
      )}
    </div>
  );
}
