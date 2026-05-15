"use client";

import { useEffect, useRef } from "react";

/**
 * Simple QR code rendered onto a canvas via the api.qrserver.com image API.
 * Kept as a small leaf component so it can be co-located with the embed
 * preview surface without bloating the dialog file.
 */
export function QRCode({ value }: { value: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !value) return;

    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      canvas.width = 128;
      canvas.height = 128;
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, 128, 128);
      ctx.drawImage(img, 0, 0, 128, 128);
    };
    img.src = `https://api.qrserver.com/v1/create-qr-code/?size=128x128&data=${encodeURIComponent(value)}`;
  }, [value]);

  return (
    <div className="flex items-center gap-3">
      <canvas
        ref={canvasRef}
        width={128}
        height={128}
        className="rounded-lg border"
        style={{ width: 96, height: 96 }}
      />
      <p className="text-xs text-muted-foreground">
        Scan to open the agent on any device
      </p>
    </div>
  );
}
