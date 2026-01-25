"use client";

import { User, Bot } from "lucide-react";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";

interface TranscriptEntry {
  role: "user" | "agent";
  text: string;
}

interface TranscriptViewerProps {
  transcript: string;
  maxHeight?: string;
  className?: string;
}

/**
 * Parse transcript string into structured entries.
 * Supports both JSON format and plain text format.
 */
function parseTranscript(transcript: string): TranscriptEntry[] {
  // Try parsing as JSON array first
  try {
    const parsed = JSON.parse(transcript);
    if (Array.isArray(parsed)) {
      return parsed.map((entry) => ({
        // Handle both "agent" and "assistant" roles
        role: entry.role === "user" ? "user" : "agent",
        text: String(entry.text || entry.content || ""),
      }));
    }
  } catch {
    // Not valid JSON, fall through to plain text parsing
  }

  // Fall back to plain text parsing
  // Common patterns: "Agent: ..." / "User: ..." or "Customer: ..." / "Contact: ..."
  const lines = transcript.split("\n").filter((line) => line.trim());
  const entries: TranscriptEntry[] = [];

  for (const line of lines) {
    const lowerLine = line.toLowerCase();
    if (
      lowerLine.startsWith("agent:") ||
      lowerLine.startsWith("assistant:") ||
      lowerLine.startsWith("ai:") ||
      lowerLine.startsWith("bot:")
    ) {
      entries.push({
        role: "agent",
        text: line.replace(/^(agent|assistant|ai|bot):\s*/i, ""),
      });
    } else if (
      lowerLine.startsWith("user:") ||
      lowerLine.startsWith("customer:") ||
      lowerLine.startsWith("contact:") ||
      lowerLine.startsWith("caller:") ||
      lowerLine.startsWith("human:")
    ) {
      entries.push({
        role: "user",
        text: line.replace(/^(user|customer|contact|caller|human):\s*/i, ""),
      });
    } else if (entries.length > 0) {
      // Continuation of previous entry
      entries[entries.length - 1].text += " " + line.trim();
    } else {
      // Unknown format, treat as user message
      entries.push({ role: "user", text: line.trim() });
    }
  }

  return entries;
}

export function TranscriptViewer({
  transcript,
  maxHeight = "200px",
  className,
}: TranscriptViewerProps) {
  const entries = parseTranscript(transcript);

  if (entries.length === 0) {
    return (
      <div className="text-sm text-muted-foreground italic">
        No transcript available
      </div>
    );
  }

  return (
    <ScrollArea
      className={cn("rounded-md border", className)}
      style={{ maxHeight }}
    >
      <div className="p-3 space-y-3">
        {entries.map((entry, index) => (
          <div
            key={index}
            className={cn(
              "flex gap-2",
              entry.role === "user" ? "justify-end" : "justify-start"
            )}
          >
            {entry.role === "agent" && (
              <div className="flex-shrink-0 size-6 rounded-full bg-purple-500/10 flex items-center justify-center">
                <Bot className="size-3.5 text-purple-500" />
              </div>
            )}
            <div
              className={cn(
                "max-w-[85%] rounded-lg px-3 py-2 text-sm",
                entry.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted"
              )}
            >
              {entry.text}
            </div>
            {entry.role === "user" && (
              <div className="flex-shrink-0 size-6 rounded-full bg-blue-500/10 flex items-center justify-center">
                <User className="size-3.5 text-blue-500" />
              </div>
            )}
          </div>
        ))}
      </div>
    </ScrollArea>
  );
}
