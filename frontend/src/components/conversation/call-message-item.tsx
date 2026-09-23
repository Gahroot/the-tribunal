"use client";

import {
  PhoneIncoming,
  PhoneOutgoing,
  PlayCircle,
} from "lucide-react";

import { TranscriptViewer } from "@/components/calls/transcript-viewer";
import { AudioPlayer } from "@/components/ui/audio-player";
import { StatusBadge } from "@/components/ui/status-badge";
import { callStatusDotColors } from "@/lib/status-colors";
import type { TimelineItem } from "@/types";

interface CallMessageItemProps {
  item: TimelineItem;
  isOutbound: boolean;
}

function formatDuration(seconds?: number): string {
  if (!seconds) return "";
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

const callStatusLabels: Record<string, string> = {
  completed: "Completed",
  failed: "Failed",
  no_answer: "No Answer",
  busy: "Busy",
  voicemail: "Voicemail",
  in_progress: "In Progress",
  initiated: "Initiated",
  ringing: "Ringing",
};

const callBadgeDotColors: Record<string, string> = {
  ...callStatusDotColors,
  voicemail: "bg-info",
};

const sentimentDotColors: Record<"positive" | "neutral" | "negative", string> = {
  positive: "bg-success",
  neutral: "bg-muted-foreground",
  negative: "bg-destructive",
};

function unavailableRecordingLabel(status?: string): string | null {
  switch (status) {
    case "completed":
      return "Recording not available";
    case "no_answer":
      return "No recording - call not answered";
    case "busy":
      return "No recording - line busy";
    case "failed":
      return "No recording - call failed";
    default:
      return null;
  }
}

export function CallMessageItem({ item, isOutbound }: CallMessageItemProps) {
  const sentiment = item.signals?.sentiment;
  const callSummary = item.signals?.summary;
  const callStatus = item.status
    ? callStatusLabels[item.status] ?? item.status
    : null;
  const callStatusDot = item.status
    ? callBadgeDotColors[item.status] ?? "bg-muted-foreground"
    : "bg-muted-foreground";

  const callIcon = isOutbound ? (
    <PhoneOutgoing className="h-4 w-4 text-muted-foreground" />
  ) : (
    <PhoneIncoming className="h-4 w-4 text-muted-foreground" />
  );

  const unavailableLabel = unavailableRecordingLabel(item.status);

  return (
    <div className="space-y-3">
      {/* Call header */}
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 rounded-full flex items-center justify-center">
          {callIcon}
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <p className="font-medium text-sm">
              {isOutbound ? "Outgoing Call" : "Incoming Call"}
            </p>
            {callStatus && (
              <StatusBadge
                dotClass={callStatusDot}
                className="text-[10px] px-1.5 py-0 h-4"
              >
                {callStatus}
              </StatusBadge>
            )}
            {sentiment && (
              <span title={callSummary || undefined}>
                <StatusBadge
                  dotClass={sentimentDotColors[sentiment]}
                  className="text-[10px] px-1.5 py-0 h-4 capitalize"
                >
                  {sentiment}
                </StatusBadge>
              </span>
            )}
          </div>
          {callSummary && (
            <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
              {callSummary}
            </p>
          )}
          <p className="text-xs text-muted-foreground">
            {item.status === "completed" && item.duration_seconds
              ? `Duration: ${formatDuration(item.duration_seconds)}`
              : item.status !== "completed"
                ? ""
                : "Duration: 0:00"}
          </p>
        </div>
      </div>

      {/* Recording player */}
      {item.recording_url && (
        <div className="pt-2 border-t">
          <AudioPlayer
            url={item.recording_url}
            duration={item.duration_seconds}
          />
        </div>
      )}

      {/* Recording unavailable indicator */}
      {!item.recording_url && unavailableLabel && (
        <div className="pt-2 border-t">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <PlayCircle className="h-4 w-4" />
            <span>{unavailableLabel}</span>
          </div>
        </div>
      )}

      {/* Transcript */}
      {item.transcript && (
        <div className="pt-2 border-t">
          <TranscriptViewer
            transcript={item.transcript}
            maxHeight="400px"
            collapsible
            defaultExpanded={false}
          />
        </div>
      )}
    </div>
  );
}
