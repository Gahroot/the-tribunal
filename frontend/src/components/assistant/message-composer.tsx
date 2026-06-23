"use client";

import { ImagePlus, Send, Square, X } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { IMAGE_ACCEPT_ATTR, readImageFile } from "@/lib/ai/image-upload";

export function MessageComposer({
  input,
  isStreaming,
  canSend,
  imageDataUrl,
  onInputChange,
  onImageChange,
  onSubmit,
  onKeyDown,
  onStop,
}: {
  input: string;
  isStreaming: boolean;
  canSend: boolean;
  imageDataUrl: string | null;
  onInputChange: (value: string) => void;
  onImageChange: (value: string | null) => void;
  onSubmit: (event: React.FormEvent) => void;
  onKeyDown: (event: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  onStop: () => void;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [imageError, setImageError] = useState<string | null>(null);

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const { dataUrl, error } = await readImageFile(file);
    if (error || !dataUrl) {
      setImageError(error ?? "Could not read the image file.");
      return;
    }
    setImageError(null);
    onImageChange(dataUrl);
  };

  return (
    <form onSubmit={onSubmit} className="border-t bg-background/95 p-4">
      {imageDataUrl ? (
        <div className="mb-2 inline-flex">
          <div className="relative">
            {/* eslint-disable-next-line @next/next/no-img-element -- local preview of a data URL */}
            <img
              src={imageDataUrl}
              alt="Attachment preview"
              className="max-h-24 w-auto rounded-lg border"
            />
            <button
              type="button"
              onClick={() => onImageChange(null)}
              aria-label="Remove image"
              className="absolute -right-2 -top-2 flex size-5 items-center justify-center rounded-full bg-foreground text-background shadow"
            >
              <X className="size-3" />
            </button>
          </div>
        </div>
      ) : null}
      {imageError ? (
        <p className="mb-2 text-xs text-destructive">{imageError}</p>
      ) : null}
      <div className="flex items-end gap-2">
        <input
          ref={fileInputRef}
          type="file"
          accept={IMAGE_ACCEPT_ATTR}
          className="hidden"
          onChange={(event) => void handleFileChange(event)}
        />
        <Button
          type="button"
          size="icon"
          variant="outline"
          onClick={() => fileInputRef.current?.click()}
          disabled={!canSend || isStreaming}
          aria-label="Attach image"
        >
          <ImagePlus className="size-4" />
        </Button>
        <Textarea
          value={input}
          onChange={(event) => onInputChange(event.target.value)}
          placeholder="Ask your CRM assistant…"
          className="max-h-[140px] min-h-[48px] resize-none"
          rows={1}
          onKeyDown={onKeyDown}
          disabled={!canSend}
        />
        {isStreaming ? (
          <Button type="button" size="icon" variant="secondary" onClick={onStop}>
            <Square className="size-4" />
            <span className="sr-only">Stop streaming</span>
          </Button>
        ) : (
          <Button
            type="submit"
            size="icon"
            disabled={(!input.trim() && !imageDataUrl) || !canSend}
            aria-label="Send message"
          >
            <Send className="size-4" />
          </Button>
        )}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        Press Enter to send, Shift+Enter for a new line. Attach a photo for the assistant to read.
      </p>
    </form>
  );
}
