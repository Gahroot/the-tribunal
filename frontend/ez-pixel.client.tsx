"use client";
// Client-only pixel init. Rendered from the root layout. The "use client"
// directive guarantees this module never executes during server-side
// rendering — `window.onerror` references would otherwise crash builds.
import { initPixel } from "@prestyj/pixel/browser";
import { useEffect } from "react";

let inited = false;

export default function EZPixelClient() {
  useEffect(() => {
    if (inited) return;
    inited = true;
    initPixel({
      projectKey: "pk_live_c300992585576c6cf817ab7d6ae29792",
      ingestUrl: "https://pixel-server.ngrout70.workers.dev",
    });
  }, []);
  return null;
}
