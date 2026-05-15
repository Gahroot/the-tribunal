"use client";

import dynamic from "next/dynamic";

/**
 * Lazy-loaded wrapper around `EmbedPreview`.
 *
 * The preview only renders when the embed dialog is open AND embedding is
 * enabled, so there's no point shipping the iframe scaffolding (or running
 * its module side effects) on the agents list page. `ssr: false` keeps the
 * fallback skeleton stable across hydration.
 */
export const EmbedPreviewLazy = dynamic(() => import("./embed-preview"), {
  ssr: false,
  loading: () => (
    <div className="min-w-0 space-y-2 lg:w-[45%]">
      <div className="h-4 w-24 animate-pulse rounded bg-muted/60" />
      <div className="h-[400px] animate-pulse rounded-xl border bg-muted/30" />
    </div>
  ),
});
