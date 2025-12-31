"use client";

import * as React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { format, isToday, isYesterday, isSameDay } from "date-fns";
import { Send, Paperclip, Mic, Phone, MoreVertical, MessageSquare } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { useContactStore } from "@/lib/contact-store";
import { MessageItem } from "./message-item";
import type { TimelineItem } from "@/types";

interface ConversationFeedProps {
  className?: string;
}

function formatDateLabel(date: Date): string {
  if (isToday(date)) return "Today";
  if (isYesterday(date)) return "Yesterday";
  return format(date, "MMMM d, yyyy");
}

function DateSeparator({ date }: { date: Date }) {
  return (
    <div className="flex items-center gap-4 py-4 px-4">
      <Separator className="flex-1" />
      <span className="text-xs text-muted-foreground font-medium">
        {formatDateLabel(date)}
      </span>
      <Separator className="flex-1" />
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center p-8">
      <div className="h-16 w-16 rounded-full bg-muted flex items-center justify-center mb-4">
        <MessageSquare className="h-8 w-8 text-muted-foreground" />
      </div>
      <h3 className="font-medium text-lg mb-2">No conversation yet</h3>
      <p className="text-sm text-muted-foreground max-w-sm">
        Start a conversation by sending a message, making a call, or scheduling an appointment.
      </p>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4 p-4">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className={cn("flex gap-3", i % 2 === 0 ? "flex-row" : "flex-row-reverse")}>
          <Skeleton className="h-8 w-8 rounded-full shrink-0" />
          <Skeleton className={cn("h-16 rounded-2xl", i % 2 === 0 ? "w-48" : "w-64")} />
        </div>
      ))}
    </div>
  );
}

export function ConversationFeed({ className }: ConversationFeedProps) {
  const { selectedContact, timeline, isLoadingTimeline } = useContactStore();
  const [message, setMessage] = React.useState("");
  const scrollAreaRef = React.useRef<HTMLDivElement>(null);
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom when new messages arrive
  React.useEffect(() => {
    if (scrollAreaRef.current) {
      const scrollContainer = scrollAreaRef.current.querySelector("[data-radix-scroll-area-viewport]");
      if (scrollContainer) {
        scrollContainer.scrollTop = scrollContainer.scrollHeight;
      }
    }
  }, [timeline]);

  // Group timeline items by date
  const groupedTimeline = React.useMemo(() => {
    const groups: { date: Date; items: TimelineItem[] }[] = [];

    timeline.forEach((item) => {
      const itemDate = new Date(item.timestamp);
      const lastGroup = groups[groups.length - 1];

      if (lastGroup && isSameDay(new Date(lastGroup.date), itemDate)) {
        lastGroup.items.push(item);
      } else {
        groups.push({ date: itemDate, items: [item] });
      }
    });

    return groups;
  }, [timeline]);

  const handleSendMessage = () => {
    if (!message.trim() || !selectedContact) return;

    // TODO: Implement send message API call
    console.log("Sending message:", message);
    setMessage("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const contactName = selectedContact
    ? [selectedContact.first_name, selectedContact.last_name].filter(Boolean).join(" ")
    : undefined;

  if (!selectedContact) {
    return (
      <div className={cn("flex flex-col h-full items-center justify-center", className)}>
        <div className="h-16 w-16 rounded-full bg-muted flex items-center justify-center mb-4">
          <MessageSquare className="h-8 w-8 text-muted-foreground" />
        </div>
        <h3 className="font-medium text-lg mb-2">Select a contact</h3>
        <p className="text-sm text-muted-foreground">
          Choose a contact to view their conversation history
        </p>
      </div>
    );
  }

  return (
    <div className={cn("flex flex-col h-full", className)}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div className="flex items-center gap-3">
          <h2 className="font-semibold">{contactName}</h2>
          {selectedContact.phone_number && (
            <span className="text-sm text-muted-foreground">
              {selectedContact.phone_number}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Button size="icon" variant="ghost" className="h-8 w-8">
            <Phone className="h-4 w-4" />
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="icon" variant="ghost" className="h-8 w-8">
                <MoreVertical className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem>View contact details</DropdownMenuItem>
              <DropdownMenuItem>Schedule appointment</DropdownMenuItem>
              <DropdownMenuItem>Add note</DropdownMenuItem>
              <DropdownMenuItem className="text-destructive">Archive</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Messages */}
      <ScrollArea ref={scrollAreaRef} className="flex-1">
        {isLoadingTimeline ? (
          <LoadingSkeleton />
        ) : timeline.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="py-4">
            <AnimatePresence mode="popLayout">
              {groupedTimeline.map((group, groupIndex) => (
                <div key={group.date.toISOString()}>
                  <DateSeparator date={group.date} />
                  {group.items.map((item) => (
                    <MessageItem
                      key={item.id}
                      item={item}
                      contactName={contactName}
                    />
                  ))}
                </div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </ScrollArea>

      {/* Message Input */}
      <div className="p-4 border-t">
        <div className="flex items-end gap-2">
          <Button size="icon" variant="ghost" className="h-9 w-9 shrink-0">
            <Paperclip className="h-4 w-4" />
          </Button>
          <div className="flex-1 relative">
            <Textarea
              ref={textareaRef}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type a message..."
              className="min-h-[40px] max-h-[120px] resize-none pr-12"
              rows={1}
            />
            <Button
              size="icon"
              variant="ghost"
              className="absolute right-1 bottom-1 h-8 w-8"
            >
              <Mic className="h-4 w-4" />
            </Button>
          </div>
          <Button
            size="icon"
            className="h-9 w-9 shrink-0"
            onClick={handleSendMessage}
            disabled={!message.trim()}
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
