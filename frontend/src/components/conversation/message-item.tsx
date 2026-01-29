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
    color: "text-green-500 bg-green-500/10",
  },
  failed: {
    icon: <X className="h-3 w-3" />,
    label: "Failed",
    color: "text-red-500 bg-red-500/10",
  },
  no_answer: {
    icon: <PhoneMissed className="h-3 w-3" />,
    label: "No Answer",
    color: "text-yellow-500 bg-yellow-500/10",
  },
  busy: {
    icon: <PhoneMissed className="h-3 w-3" />,
    label: "Busy",
    color: "text-yellow-500 bg-yellow-500/10",
  },
  voicemail: {
    icon: <Voicemail className="h-3 w-3" />,
    label: "Voicemail",
    color: "text-blue-500 bg-blue-500/10",
  },
  in_progress: {
    icon: <Phone className="h-3 w-3" />,
    label: "In Progress",
    color: "text-blue-500 bg-blue-500/10",
  },
  initiated: {
    icon: <Clock className="h-3 w-3" />,
    label: "Initiated",
    color: "text-muted-foreground bg-muted",
  },
  ringing: {
    icon: <Phone className="h-3 w-3" />,
    label: "Ringing",
    color: "text-blue-500 bg-blue-500/10",
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
      <PhoneOutgoing className="h-4 w-4 text-green-500" />
    ) : (
      <PhoneIncoming className="h-4 w-4 text-blue-500" />
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
        "flex gap-3 px-4 py-2",
        isOutbound ? "flex-row-reverse" : "flex-row"
      )}
    >
      {/* Avatar */}
      <Avatar className="h-8 w-8 shrink-0">
        <AvatarFallback
          className={cn(
            "text-xs",
            item.is_ai
              ? "bg-purple-500/10 text-purple-500"
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
            "flex items-center gap-2 mb-1 text-xs text-muted-foreground",
            isOutbound ? "flex-row-reverse" : "flex-row"
          )}
        >
          {item.is_ai && (
            <Badge
              variant="secondary"
              className="text-[10px] px-1.5 py-0 h-4 bg-purple-500/10 text-purple-500"
            >
              AI
            </Badge>
          )}
          <span>{timestamp}</span>
          {channelIcons[item.type]}
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
                    isOutbound ? "bg-green-500/10" : "bg-blue-500/10"
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

              {/* Transcript */}
              {item.transcript && (
                <div className="pt-2 border-t">
                  <TranscriptViewer
                    transcript={item.transcript}
                    maxHeight="200px"
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
              <div className="h-10 w-10 rounded-full bg-blue-500/10 flex items-center justify-center">
                <Calendar className="h-4 w-4 text-blue-500" />
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
