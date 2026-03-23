"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { format } from "date-fns";
import {
  Phone,
  PhoneIncoming,
  PhoneOutgoing,
  MessageSquare,
  Mail,
  Voicemail,
  Bot,
  User,
  Calendar,
  FileText,
  Check,
  X,
  Clock,
  PhoneMissed,
  PlayCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { AudioPlayer } from "@/components/ui/audio-player";
import { TranscriptViewer } from "@/components/calls/transcript-viewer";
import type { TimelineItem } from "@/types";

interface MessageItemProps {
  item: TimelineItem;
  contactName?: string;
}

const channelIcons: Record<string, React.ReactNode> = {
  sms: <MessageSquare className="h-4 w-4" />,
  call: <Phone className="h-4 w-4" />,
  email: <Mail className="h-4 w-4" />,
  voicemail: <Voicemail className="h-4 w-4" />,
  appointment: <Calendar className="h-4 w-4" />,
  note: <FileText className="h-4 w-4" />,
};

function formatDuration(seconds?: number): string {
  if (!seconds) return "";
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

// Call status configuration
const callStatusConfig: Record<
  string,
  { icon: React.ReactNode; label: string; color: string }
> = {
  completed: {
    icon: <Check className="h-3 w-3" />,
    label: "Completed",
    color: "text-success bg-success/10",
  },
  failed: {
    icon: <X className="h-3 w-3" />,
    label: "Failed",
    color: "text-destructive bg-destructive/10",
  },
  no_answer: {
    icon: <PhoneMissed className="h-3 w-3" />,
    label: "No Answer",
    color: "text-warning bg-warning/10",
  },
  busy: {
    icon: <PhoneMissed className="h-3 w-3" />,
    label: "Busy",
    color: "text-warning bg-warning/10",
  },
  voicemail: {
    icon: <Voicemail className="h-3 w-3" />,
    label: "Voicemail",
    color: "text-info bg-info/10",
  },
  in_progress: {
    icon: <Phone className="h-3 w-3" />,
    label: "In Progress",
    color: "text-info bg-info/10",
  },
  initiated: {
    icon: <Clock className="h-3 w-3" />,
    label: "Initiated",
    color: "text-muted-foreground bg-muted",
  },
  ringing: {
    icon: <Phone className="h-3 w-3" />,
    label: "Ringing",
    color: "text-info bg-info/10",
  },
};

export function MessageItem({ item, contactName }: MessageItemProps) {
  const isOutbound = item.direction === "outbound";
  const isCall = item.type === "call";
  const isAppointment = item.type === "appointment";

  // Format timestamp
  const timestamp = format(new Date(item.timestamp), "h:mm a");

  // Call-specific icon
  const callIcon = isCall ? (
    isOutbound ? (
      <PhoneOutgoing className="h-4 w-4 text-success" />
    ) : (
      <PhoneIncoming className="h-4 w-4 text-info" />
    )
  ) : null;

  // Get call status info
  const callStatus = item.status
    ? callStatusConfig[item.status] ?? {
        icon: <Phone className="h-3 w-3" />,
        label: item.status,
        color: "text-muted-foreground bg-muted",
      }
    : null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={cn(
        "flex gap-3 px-4 py-2 overflow-hidden",
        isOutbound ? "flex-row-reverse" : "flex-row"
      )}
    >
      {/* Avatar */}
      <Avatar className="h-8 w-8 shrink-0">
        <AvatarFallback
          className={cn(
            "text-xs",
            item.is_ai
              ? "bg-primary/10 text-primary"
              : isOutbound
                ? "bg-primary/10 text-primary"
                : "bg-muted"
          )}
        >
          {item.is_ai ? (
            <Bot className="h-4 w-4" />
          ) : isOutbound ? (
            "You"
          ) : (
            contactName?.[0]?.toUpperCase() ?? <User className="h-4 w-4" />
          )}
        </AvatarFallback>
      </Avatar>

      {/* Message Bubble */}
      <div
        className={cn(
          "flex flex-col max-w-[70%]",
          isOutbound ? "items-end" : "items-start"
        )}
      >
        {/* Sender info */}
        <div
          className={cn(
            "flex items-center gap-2 mb-1 text-xs text-muted-foreground overflow-hidden",
            isOutbound ? "flex-row-reverse" : "flex-row"
          )}
        >
          {item.is_ai && (
            <Badge
              variant="secondary"
              className="text-[10px] px-1.5 py-0 h-4 bg-primary/10 text-primary shrink-0"
            >
              AI
            </Badge>
          )}
          <span className="shrink-0">{timestamp}</span>
          <span className="shrink-0">{channelIcons[item.type]}</span>
        </div>

        {/* Content bubble */}
        <div
          className={cn(
            "rounded-2xl px-4 py-2.5",
            isCall || isAppointment
              ? "bg-muted/50 border"
              : isOutbound
                ? "bg-primary text-primary-foreground"
                : "bg-muted"
          )}
        >
          {/* Call content */}
          {isCall && (
            <div className="space-y-3">
              {/* Call header */}
              <div className="flex items-center gap-3">
                <div
                  className={cn(
                    "h-10 w-10 rounded-full flex items-center justify-center",
                    isOutbound ? "bg-success/10" : "bg-info/10"
                  )}
                >
                  {callIcon}
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <p className="font-medium text-sm">
                      {isOutbound ? "Outgoing Call" : "Incoming Call"}
                    </p>
                    {callStatus && (
                      <Badge
                        variant="secondary"
                        className={cn(
                          "text-[10px] px-1.5 py-0 h-4 gap-0.5",
                          callStatus.color
                        )}
                      >
                        {callStatus.icon}
                        <span className="ml-0.5">{callStatus.label}</span>
                      </Badge>
                    )}
                  </div>
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
              {!item.recording_url && isCall && (
                <div className="pt-2 border-t">
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <PlayCircle className="h-4 w-4" />
                    <span>
                      {item.status === "completed"
                        ? "Recording not available"
                        : item.status === "no_answer"
                          ? "No recording - call not answered"
                          : item.status === "busy"
                            ? "No recording - line busy"
                            : item.status === "failed"
                              ? "No recording - call failed"
                              : null}
                    </span>
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
          )}

          {/* Appointment content */}
          {isAppointment && (
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-info/10 flex items-center justify-center">
                <Calendar className="h-4 w-4 text-info" />
              </div>
              <div className="flex-1">
                <p className="font-medium text-sm">Appointment Scheduled</p>
                <p className="text-xs text-muted-foreground">{item.content}</p>
              </div>
            </div>
          )}

          {/* Text content */}
          {!isCall && !isAppointment && (
            <p className="text-sm whitespace-pre-wrap break-words">
              {item.content}
            </p>
          )}
        </div>
      </div>
    </motion.div>
  );
}
