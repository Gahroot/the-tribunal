"use client";

import { Download, ExternalLink, PlayCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import type {
  CalculatorContent,
  LeadMagnet,
  QuizContent,
  RichTextContent,
} from "@/types";

import { CalculatorRunner } from "./calculator-runner";
import { QuizRunner } from "./quiz-runner";

interface LeadMagnetContentProps {
  magnet: Pick<
    LeadMagnet,
    "magnet_type" | "delivery_method" | "content_url" | "content_data" | "name"
  >;
}

function downloadLabel(magnet: LeadMagnetContentProps["magnet"]): {
  label: string;
  icon: React.ReactNode;
} {
  switch (magnet.delivery_method) {
    case "redirect":
      return { label: "Open", icon: <ExternalLink className="size-4 mr-2" /> };
    case "download":
      return { label: "Download", icon: <Download className="size-4 mr-2" /> };
    default:
      if (magnet.magnet_type === "video" || magnet.magnet_type === "webinar") {
        return { label: "Watch", icon: <PlayCircle className="size-4 mr-2" /> };
      }
      return { label: "Access", icon: <Download className="size-4 mr-2" /> };
  }
}

/**
 * Renders the consumable content of a lead magnet so a prospect can actually
 * interact with or download it. Used on the public offer page and in the
 * creator-facing preview dialog. A standalone public renderer route is a
 * larger, separate effort; this makes attached magnets reachable today.
 */
export function LeadMagnetContent({ magnet }: LeadMagnetContentProps) {
  const { magnet_type, content_url, content_data } = magnet;

  if (magnet_type === "quiz" && content_data) {
    return <QuizRunner content={content_data as QuizContent} />;
  }

  if (magnet_type === "calculator" && content_data) {
    return <CalculatorRunner content={content_data as CalculatorContent} />;
  }

  if (magnet_type === "rich_text" && content_data) {
    const rich = content_data as RichTextContent;
    return (
      <div className="space-y-2">
        {rich.title && <h4 className="font-semibold">{rich.title}</h4>}
        {rich.description && (
          <p className="text-sm text-muted-foreground">{rich.description}</p>
        )}
        {content_url && <DownloadButton magnet={magnet} />}
      </div>
    );
  }

  if (content_url) {
    return <DownloadButton magnet={magnet} />;
  }

  return (
    <p className="text-sm text-muted-foreground">
      This bonus will be delivered after you sign up.
    </p>
  );
}

function DownloadButton({ magnet }: LeadMagnetContentProps) {
  const { label, icon } = downloadLabel(magnet);
  return (
    <Button asChild size="sm">
      <a
        href={magnet.content_url}
        target="_blank"
        rel="noopener noreferrer"
        download={magnet.delivery_method === "download" ? "" : undefined}
      >
        {icon}
        {label}
      </a>
    </Button>
  );
}
