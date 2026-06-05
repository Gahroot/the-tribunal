"use client";

import { useMutation } from "@tanstack/react-query";
import { Loader2, Send, Trophy } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { roleplayApi } from "@/lib/api/roleplay";
import { getApiErrorMessage } from "@/lib/utils/errors";
import type { RehearsalRun } from "@/types/roleplay";

interface RehearsalChatProps {
  workspaceId: string;
  run: RehearsalRun;
  onUpdate: (run: RehearsalRun) => void;
  onScored: (run: RehearsalRun) => void;
}

export function RehearsalChat({
  workspaceId,
  run,
  onUpdate,
  onScored,
}: RehearsalChatProps) {
  const [message, setMessage] = useState("");

  const turnMutation = useMutation({
    mutationFn: (text: string) => roleplayApi.advanceTurn(workspaceId, run.id, text),
    onSuccess: (updated) => {
      setMessage("");
      onUpdate(updated);
    },
    onError: (err: unknown) => {
      toast.error(getApiErrorMessage(err, "Failed to send message"));
    },
  });

  const scoreMutation = useMutation({
    mutationFn: () => roleplayApi.scoreRun(workspaceId, run.id),
    onSuccess: (scored) => {
      onScored(scored);
      toast.success("Rehearsal scored");
    },
    onError: (err: unknown) => {
      toast.error(getApiErrorMessage(err, "Failed to score rehearsal"));
    },
  });

  const busy = turnMutation.isPending;
  const repTurns = run.transcript.filter((t) => t.role === "agent").length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">
          Practicing against {run.persona_name ?? "the prospect"}
        </CardTitle>
        <p className="text-sm text-muted-foreground">
          You are the rep. Reply to the prospect, then finish to get scored.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="max-h-[420px] space-y-3 overflow-y-auto rounded-md border p-3">
          {run.transcript.map((turn, i) => {
            const isProspect = turn.role === "prospect";
            return (
              <div
                key={i}
                className={`flex ${isProspect ? "justify-start" : "justify-end"}`}
              >
                <div
                  className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                    isProspect ? "bg-muted" : "bg-primary text-primary-foreground"
                  }`}
                >
                  <div className="mb-1 text-xs opacity-70">
                    {isProspect ? run.persona_name ?? "Prospect" : "You"}
                  </div>
                  {turn.content}
                </div>
              </div>
            );
          })}
          {busy ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Prospect is replying…
            </div>
          ) : null}
        </div>

        <div className="flex flex-col gap-2">
          <Textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Type your reply to the prospect…"
            rows={3}
            disabled={busy}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && message.trim()) {
                e.preventDefault();
                turnMutation.mutate(message.trim());
              }
            }}
          />
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-muted-foreground">
              {repTurns} repl{repTurns === 1 ? "y" : "ies"} sent · ⌘/Ctrl+Enter to send
            </span>
            <div className="flex gap-2">
              <Button
                variant="outline"
                disabled={repTurns === 0 || scoreMutation.isPending}
                onClick={() => scoreMutation.mutate()}
              >
                {scoreMutation.isPending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Trophy className="size-4" />
                )}
                Finish &amp; score
              </Button>
              <Button
                disabled={!message.trim() || busy}
                onClick={() => turnMutation.mutate(message.trim())}
              >
                <Send className="size-4" />
                Send
              </Button>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
