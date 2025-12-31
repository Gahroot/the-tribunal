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
  Play,
  Pause,
  Bot,
  User,
  Calendar,
  FileText
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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

function AudioPlayer({ url }: { url: string }) {
  const [isPlaying, setIsPlaying] = React.useState(false);
  const audioRef = React.useRef<HTMLAudioElement>(null);

  const togglePlayback = () => {
    if (!audioRef.current) return;

    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play();
    }
    setIsPlaying(!isPlaying);
  };

  return (
    <div className="flex items-center gap-2 mt-2">
      <audio
        ref={audioRef}
        src={url}
        onEnded={() => setIsPlaying(false)}
        className="hidden"
      />
      <Button
        size="icon"
        variant="secondary"
        className="h-8 w-8 rounded-full"
        onClick={togglePlayback}
      >
        {isPlaying ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
      </Button>
      <div className="flex-1 h-1 bg-muted rounded-full overflow-hidden">
        <div className="h-full w-1/3 bg-primary rounded-full" />
      </div>
    </div>
  );
}

export function MessageItem({ item, contactName }: MessageItemProps) {
  const isOutbound = item.direction === "outbound";
  const isCall = item.type === "call";
  const isAppointment = item.type === "appointment";

  // Format timestamp
  const timestamp = format(new Date(item.timestamp), "h:mm a");
  const dateLabel = format(new Date(item.timestamp), "MMM d");

  // Call-specific icon
  const callIcon = isCall ? (
    isOutbound ? (
      <PhoneOutgoing className="h-4 w-4 text-green-500" />
    ) : (
      <PhoneIncoming className="h-4 w-4 text-blue-500" />
    )
  ) : null;

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
        <AvatarFallback className={cn(
          "text-xs",
          item.is_ai ? "bg-purple-500/10 text-purple-500" :
          isOutbound ? "bg-primary/10 text-primary" : "bg-muted"
        )}>
          {item.is_ai ? <Bot className="h-4 w-4" /> :
           isOutbound ? "You" : contactName?.[0]?.toUpperCase() ?? <User className="h-4 w-4" />}
        </AvatarFallback>
      </Avatar>

      {/* Message Bubble */}
      <div className={cn(
        "flex flex-col max-w-[70%]",
        isOutbound ? "items-end" : "items-start"
      )}>
        {/* Sender info */}
        <div className={cn(
          "flex items-center gap-2 mb-1 text-xs text-muted-foreground",
          isOutbound ? "flex-row-reverse" : "flex-row"
        )}>
          {item.is_ai && (
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-4 bg-purple-500/10 text-purple-500">
              AI
            </Badge>
          )}
          <span>{timestamp}</span>
          {channelIcons[item.type]}
        </div>

        {/* Content bubble */}
        <div className={cn(
          "rounded-2xl px-4 py-2.5",
          isCall || isAppointment ? "bg-muted/50 border" :
          isOutbound ? "bg-primary text-primary-foreground" : "bg-muted"
        )}>
          {/* Call content */}
          {isCall && (
            <div className="flex items-center gap-3">
              <div className={cn(
                "h-10 w-10 rounded-full flex items-center justify-center",
                isOutbound ? "bg-green-500/10" : "bg-blue-500/10"
              )}>
                {callIcon}
              </div>
              <div className="flex-1">
                <p className="font-medium text-sm">
                  {isOutbound ? "Outgoing Call" : "Incoming Call"}
                </p>
                <p className="text-xs text-muted-foreground">
                  {item.status === "completed"
                    ? `Duration: ${formatDuration(item.duration_seconds)}`
                    : item.status}
                </p>
              </div>
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
            <p className="text-sm whitespace-pre-wrap break-words">{item.content}</p>
          )}

          {/* Recording player for calls */}
          {isCall && item.recording_url && (
            <AudioPlayer url={item.recording_url} />
          )}

          {/* Transcript for calls */}
          {isCall && item.transcript && (
            <div className="mt-3 pt-3 border-t">
              <p className="text-xs font-medium mb-1 text-muted-foreground">Transcript</p>
              <p className="text-xs text-muted-foreground whitespace-pre-wrap">
                {item.transcript}
              </p>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}
