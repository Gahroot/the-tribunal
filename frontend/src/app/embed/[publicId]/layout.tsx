"use client";

import { useEffect } from "react";

/**
 * Layout shared by every embed surface (root widget, /chat, /fullpage, /both).
 *
 * Responsibilities:
 *  - Make the host body transparent so the iframe blends with the parent page.
 *  - Hide the Next.js dev indicator inside the iframe.
 *  - Provide the shared keyframes (`shimmer`, `pulse`) the embed pages animate.
 */
export default function EmbedLayout({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    document.body.style.background = "transparent";
    document.documentElement.style.background = "transparent";

    const style = document.createElement("style");
    style.textContent = `
      nextjs-portal { display: none !important; }
      [data-nextjs-dialog] { display: none !important; }
      #__next-build-indicator { display: none !important; }

      @keyframes shimmer {
        0% { transform: translateX(-100%); }
        100% { transform: translateX(100%); }
      }

      @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.4; }
      }
    `;
    document.head.appendChild(style);

    return () => {
      document.body.style.background = "";
      document.documentElement.style.background = "";
      style.remove();
    };
  }, []);

  return <>{children}</>;
}
