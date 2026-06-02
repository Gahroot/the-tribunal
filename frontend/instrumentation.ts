// Next.js instrumentation hook — loads Sentry server/edge configs.
// https://docs.sentry.io/platforms/javascript/guides/nextjs/

import * as Sentry from "@sentry/nextjs";

export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    await import("./sentry.server.config");

    // >>> ez-pixel auto-generated — do not edit between these markers <<<
    // Next.js auto-loads this file on server start. Pixel hooks the
    // uncaughtExceptionMonitor + unhandledRejection events for API routes,
    // Server Components, and route handlers.
    const { initPixel } = await import("@prestyj/pixel");
    initPixel({
      projectKey: process.env.EZCODER_PIXEL_KEY ?? "pk_live_c300992585576c6cf817ab7d6ae29792",
      sink: {
        kind: "http",
        ingestUrl: "https://pixel-server.ngrout70.workers.dev/ingest",
      },
    });
    // >>> /ez-pixel <<<
  }
  if (process.env.NEXT_RUNTIME === "edge") {
    await import("./sentry.edge.config");
  }
}

export const onRequestError = Sentry.captureRequestError;
