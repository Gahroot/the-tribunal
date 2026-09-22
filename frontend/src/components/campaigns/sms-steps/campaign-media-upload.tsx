"use client";

import { AlertCircle, ImagePlus, Loader2, X } from "lucide-react";
import Image from "next/image";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { IMAGE_ACCEPT_ATTR, readImageFile } from "@/lib/ai/image-upload";

export interface CampaignMedia {
  name: string;
  size: number;
  dataUrl: string;
}

interface CampaignMediaUploadProps {
  value: CampaignMedia | null;
  onChange: (media: CampaignMedia | null) => void;
}

type UploadStatus = "idle" | "loading";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Image attachment control for the campaign composer. Runs client-side
 * validation (MIME type and size) through `readImageFile` and surfaces every
 * state explicitly: idle, reading, attached (thumbnail + size + remove), and
 * an inline destructive message when validation fails.
 */
export function CampaignMediaUpload({ value, onChange }: CampaignMediaUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [status, setStatus] = useState<UploadStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const handleFile = async (file: File | undefined) => {
    if (!file) return;
    setStatus("loading");
    setError(null);
    const result = await readImageFile(file);
    if (result.error || !result.dataUrl) {
      setError(result.error ?? "Could not read the image file");
      setStatus("idle");
      return;
    }
    onChange({ name: file.name, size: file.size, dataUrl: result.dataUrl });
    setStatus("idle");
  };

  return (
    <div className="space-y-2">
      <input
        ref={inputRef}
        type="file"
        accept={IMAGE_ACCEPT_ATTR}
        className="hidden"
        aria-hidden="true"
        tabIndex={-1}
        onChange={(e) => {
          void handleFile(e.target.files?.[0]);
          e.target.value = "";
        }}
      />

      {value ? (
        <div className="flex items-center gap-3 rounded-lg border bg-background p-2">
          <Image
            src={value.dataUrl}
            alt={value.name}
            width={40}
            height={40}
            unoptimized
            className="size-10 shrink-0 rounded-md border object-cover"
          />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{value.name}</p>
            <p className="text-xs text-muted-foreground">{formatBytes(value.size)}</p>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label="Remove image"
            onClick={() => {
              onChange(null);
              setError(null);
            }}
          >
            <X className="size-4" />
          </Button>
        </div>
      ) : (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={status === "loading"}
          onClick={() => inputRef.current?.click()}
        >
          {status === "loading" ? (
            <>
              <Loader2 className="size-4 animate-spin" />
              Reading image…
            </>
          ) : (
            <>
              <ImagePlus className="size-4" />
              Add image
            </>
          )}
        </Button>
      )}

      {error && (
        <p role="alert" className="flex items-center gap-1.5 text-sm text-destructive">
          <AlertCircle className="size-4 shrink-0" />
          {error}
        </p>
      )}
    </div>
  );
}
