"use client";

import { Ear, Mic, MicOff, Send, X, Loader2 } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { useCallSupervisor } from "@/hooks/useCallSupervisor";
import { type LiveCall } from "@/lib/api/calls";
import { cn } from "@/lib/utils";

interface LiveCallSupervisorProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspaceId: string;
  call: LiveCall | null;
}

/**
 * Operator control panel for one live call: listen, whisper, and barge-in.
 *
 * Mounted from the live-call roster. Opening it connects the supervisor
 * WebSocket and begins streaming the call audio; whisper sends private AI
 * guidance; barge takes over the call with the operator's microphone.
 */
export function LiveCallSupervisor({
  open,
  onOpenChange,
  workspaceId,
  call,
}: LiveCallSupervisorProps) {
  const callId = call?.call_id ?? null;
  const { status, error, isBarging, connect, disconnect, whisper, startBarge, stopBarge } =
    useCallSupervisor({ workspaceId, callId });
  const [whisperText, setWhisperText] = useState("");

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      disconnect();
      setWhisperText("");
    }
    onOpenChange(next);
  };

  const handleSendWhisper = () => {
    if (!whisperText.trim()) return;
    whisper(whisperText);
    setWhisperText("");
  };

  const connected = status === "listening";
  const contactLabel = call?.contact_name || call?.contact_phone || "Unknown contact";

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            Supervise call
            <Badge variant={isBarging ? "destructive" : "secondary"}>
              {isBarging ? "You have the call" : "AI handling"}
            </Badge>
          </DialogTitle>
          <DialogDescription>
            {contactLabel}
            {call?.agent_name ? ` · agent ${call.agent_name}` : ""}
            {call ? ` · ${call.direction}` : ""}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-5 py-2">
          {/* Connection status */}
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "h-2.5 w-2.5 rounded-full",
                connected && "bg-success",
                status === "connecting" && "bg-warning animate-pulse",
                (status === "idle" || status === "ended") && "bg-muted-foreground",
                status === "error" && "bg-destructive"
              )}
            />
            <span className="text-sm text-muted-foreground capitalize">{status}</span>
          </div>

          {error && (
            <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          {/* Listen control */}
          {status === "idle" || status === "ended" || status === "error" ? (
            <Button onClick={() => void connect()} className="gap-2">
              <Ear className="h-4 w-4" />
              Start monitoring
            </Button>
          ) : (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              {status === "connecting" ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Ear className="h-4 w-4 text-primary" />
              )}
              {status === "connecting" ? "Connecting…" : "Listening to live audio"}
            </div>
          )}

          {/* Whisper control */}
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="whisper-input">
              Whisper to the AI
            </label>
            <p className="text-xs text-muted-foreground">
              Private guidance for the AI&apos;s next turn. The caller never hears it.
            </p>
            <div className="flex gap-2">
              <Textarea
                id="whisper-input"
                value={whisperText}
                onChange={(e) => setWhisperText(e.target.value)}
                placeholder="e.g. Offer the 10% discount and ask about timing"
                className="min-h-[60px]"
                disabled={!connected}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    handleSendWhisper();
                  }
                }}
              />
              <Button
                variant="outline"
                size="icon"
                className="h-auto"
                disabled={!connected || !whisperText.trim()}
                onClick={handleSendWhisper}
                aria-label="Send whisper"
              >
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Barge-in control */}
          <div className="space-y-2">
            <p className="text-sm font-medium">Take over the call</p>
            <p className="text-xs text-muted-foreground">
              Mutes the AI and connects your microphone to the caller.
            </p>
            {isBarging ? (
              <Button variant="destructive" className="gap-2" onClick={stopBarge}>
                <MicOff className="h-4 w-4" />
                Hand back to AI
              </Button>
            ) : (
              <Button
                variant="default"
                className="gap-2"
                disabled={!connected}
                onClick={() => void startBarge()}
              >
                <Mic className="h-4 w-4" />
                Barge in
              </Button>
            )}
          </div>
        </div>

        <div className="flex justify-end">
          <Button variant="ghost" className="gap-2" onClick={() => handleOpenChange(false)}>
            <X className="h-4 w-4" />
            Close
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
