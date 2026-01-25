"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Phone,
  PhoneOff,
  Mic,
  MicOff,
  User,
  Clock,
  Bot,
  X,
  Minimize2,
} from "lucide-react";
import { useMutation } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Card, CardContent } from "@/components/ui/card";
import { callsApi } from "@/lib/api/calls";
import type { CallRecord } from "@/types";

interface ActiveCallProps {
  call: CallRecord;
  workspaceId: string;
  contactName?: string;
  agentName?: string;
  onCallEnded?: () => void;
  onClose?: () => void;
}

function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  if (hours > 0) {
    return `${hours}:${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

function getInitials(name: string): string {
  return name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

const statusConfig: Record<
  string,
  { label: string; color: string; pulse: boolean }
> = {
  initiated: {
    label: "Connecting",
    color: "bg-blue-500/10 text-blue-500 border-blue-500/20",
    pulse: true,
  },
  ringing: {
    label: "Ringing",
    color: "bg-yellow-500/10 text-yellow-500 border-yellow-500/20",
    pulse: true,
  },
  in_progress: {
    label: "In Progress",
    color: "bg-green-500/10 text-green-500 border-green-500/20",
    pulse: true,
  },
  answered: {
    label: "Connected",
    color: "bg-green-500/10 text-green-500 border-green-500/20",
    pulse: true,
  },
  completed: {
    label: "Completed",
    color: "bg-gray-500/10 text-gray-500 border-gray-500/20",
    pulse: false,
  },
  failed: {
    label: "Failed",
    color: "bg-red-500/10 text-red-500 border-red-500/20",
    pulse: false,
  },
  busy: {
    label: "Busy",
    color: "bg-orange-500/10 text-orange-500 border-orange-500/20",
    pulse: false,
  },
  no_answer: {
    label: "No Answer",
    color: "bg-gray-500/10 text-gray-500 border-gray-500/20",
    pulse: false,
  },
};

export function ActiveCall({
  call,
  workspaceId,
  contactName,
  agentName,
  onCallEnded,
  onClose,
}: ActiveCallProps) {
  const [duration, setDuration] = useState(0);
  const [isMuted, setIsMuted] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);

  // Initialize and sync duration from call start time
  // We compute initial duration in an effect to avoid calling Date.now() during render
  useEffect(() => {
    const computeInitialDuration = () => {
      const startTime = call.answered_at
        ? new Date(call.answered_at)
        : new Date(call.started_at || call.created_at);
      return Math.max(0, Math.floor((Date.now() - startTime.getTime()) / 1000));
    };

    const frameId = requestAnimationFrame(() => {
      setDuration(computeInitialDuration());
    });
    return () => cancelAnimationFrame(frameId);
  }, [call.answered_at, call.started_at, call.created_at]);

  // Update duration every second for active calls
  useEffect(() => {
    const isActive =
      call.status === "in_progress" ||
      call.status === "ringing";

    if (!isActive) {
      return;
    }

    const interval = setInterval(() => {
      setDuration((prev) => prev + 1);
    }, 1000);

    return () => clearInterval(interval);
  }, [call.status]);

  // Hangup mutation
  const hangupMutation = useMutation({
    mutationFn: () => callsApi.hangup(workspaceId, call.id),
    onSuccess: () => {
      onCallEnded?.();
    },
    onError: (error) => {
      console.error("Failed to hangup call:", error);
    },
  });

  const handleHangup = useCallback(() => {
    hangupMutation.mutate();
  }, [hangupMutation]);

  const handleMuteToggle = useCallback(() => {
    setIsMuted((prev) => !prev);
    // Note: Actual mute functionality would require WebRTC integration
  }, []);

  const status = statusConfig[call.status] || statusConfig.initiated;
  const displayName = contactName || call.to_number || call.from_number;
  const isCallActive =
    call.status === "in_progress" ||
    call.status === "ringing" ||
    call.status === "initiated";

  // Minimized floating button view
  if (isMinimized) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.8 }}
        className="fixed bottom-4 right-4 z-50"
      >
        <Button
          variant="default"
          size="lg"
          className="h-14 w-14 rounded-full bg-green-600 hover:bg-green-700 shadow-lg"
          onClick={() => setIsMinimized(false)}
        >
          <Phone className="size-6" />
          {status.pulse && (
            <span className="absolute -top-1 -right-1 flex h-4 w-4">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-4 w-4 bg-green-500"></span>
            </span>
          )}
        </Button>
        <div className="absolute -top-8 right-0 bg-background border rounded px-2 py-1 text-xs font-mono">
          {formatDuration(duration)}
        </div>
      </motion.div>
    );
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 50 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 50 }}
        className="fixed bottom-4 right-4 z-50 w-80"
      >
        <Card className="border-2 border-primary/20 shadow-xl bg-background/95 backdrop-blur">
          <CardContent className="p-4">
            {/* Header with controls */}
            <div className="flex items-center justify-between mb-4">
              <Badge variant="outline" className={status.color}>
                {status.pulse && (
                  <span className="relative flex h-2 w-2 mr-1">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-current opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-current"></span>
                  </span>
                )}
                {status.label}
              </Badge>
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6"
                  onClick={() => setIsMinimized(true)}
                >
                  <Minimize2 className="size-3" />
                </Button>
                {onClose && !isCallActive && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    onClick={onClose}
                  >
                    <X className="size-3" />
                  </Button>
                )}
              </div>
            </div>

            {/* Contact info */}
            <div className="flex items-center gap-3 mb-4">
              <Avatar className="size-12">
                <AvatarFallback className="bg-primary/10 text-primary">
                  {contactName ? getInitials(contactName) : <User className="size-6" />}
                </AvatarFallback>
              </Avatar>
              <div className="flex-1 min-w-0">
                <div className="font-medium truncate">{displayName}</div>
                {call.direction === "inbound" ? (
                  <div className="text-xs text-muted-foreground">
                    Incoming call from {call.from_number}
                  </div>
                ) : (
                  <div className="text-xs text-muted-foreground">
                    Calling {call.to_number}
                  </div>
                )}
              </div>
            </div>

            {/* Duration */}
            <div className="flex items-center justify-center gap-2 mb-4 py-3 bg-muted/50 rounded-lg">
              <Clock className="size-4 text-muted-foreground" />
              <span className="text-2xl font-mono font-semibold">
                {formatDuration(duration)}
              </span>
            </div>

            {/* Agent info */}
            {agentName && (
              <div className="flex items-center gap-2 mb-4 text-sm text-muted-foreground">
                <Bot className="size-4" />
                <span>Handled by {agentName}</span>
              </div>
            )}

            {/* Call controls */}
            {isCallActive && (
              <div className="flex items-center justify-center gap-4">
                <Button
                  variant={isMuted ? "destructive" : "outline"}
                  size="icon"
                  className="h-12 w-12 rounded-full"
                  onClick={handleMuteToggle}
                >
                  {isMuted ? (
                    <MicOff className="size-5" />
                  ) : (
                    <Mic className="size-5" />
                  )}
                </Button>
                <Button
                  variant="destructive"
                  size="icon"
                  className="h-14 w-14 rounded-full"
                  onClick={handleHangup}
                  disabled={hangupMutation.isPending}
                >
                  <PhoneOff className="size-6" />
                </Button>
              </div>
            )}

            {/* Call ended state */}
            {!isCallActive && (
              <div className="text-center text-sm text-muted-foreground">
                <p>
                  Call {call.status === "completed" ? "ended" : call.status}
                </p>
                {call.duration_seconds && (
                  <p className="mt-1">
                    Duration: {formatDuration(call.duration_seconds)}
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </AnimatePresence>
  );
}

// Hook to manage active call state
export function useActiveCall() {
  const [activeCall, setActiveCall] = useState<CallRecord | null>(null);

  const startCall = useCallback((call: CallRecord) => {
    setActiveCall(call);
  }, []);

  const endCall = useCallback(() => {
    setActiveCall(null);
  }, []);

  const updateCall = useCallback((call: CallRecord) => {
    setActiveCall(call);
  }, []);

  return {
    activeCall,
    startCall,
    endCall,
    updateCall,
    hasActiveCall: activeCall !== null,
  };
}
