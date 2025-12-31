"use client";

import * as React from "react";
import { format } from "date-fns";
import {
  Phone,
  Mail,
  Building2,
  Calendar,
  Tag,
  FileText,
  Clock,
  ChevronRight,
  Edit2,
  Trash2,
  Bot,
  Activity,
  X
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { useContactStore } from "@/lib/contact-store";
import { useIsMobile } from "@/hooks/use-mobile";
import type { Contact } from "@/types";

interface ContactSidebarProps {
  className?: string;
  onClose?: () => void;
}

const statusColors: Record<string, string> = {
  new: "bg-blue-500",
  contacted: "bg-yellow-500",
  qualified: "bg-green-500",
  converted: "bg-purple-500",
  lost: "bg-red-500",
};

function getInitials(contact: Contact): string {
  const first = contact.first_name?.[0] ?? "";
  const last = contact.last_name?.[0] ?? "";
  return (first + last).toUpperCase() || "?";
}

interface InfoRowProps {
  icon: React.ReactNode;
  label: string;
  value?: string | null;
  onClick?: () => void;
}

function InfoRow({ icon, label, value, onClick }: InfoRowProps) {
  if (!value) return null;

  const content = (
    <div className="flex items-start gap-3 py-2">
      <div className="h-8 w-8 rounded-lg bg-muted flex items-center justify-center shrink-0">
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-sm font-medium truncate">{value}</p>
      </div>
      {onClick && <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0 mt-2" />}
    </div>
  );

  if (onClick) {
    return (
      <button onClick={onClick} className="w-full text-left hover:bg-accent/50 rounded-lg px-2 -mx-2 transition-colors">
        {content}
      </button>
    );
  }

  return <div className="px-2 -mx-2">{content}</div>;
}

interface QuickActionProps {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  variant?: "default" | "primary" | "destructive";
}

function QuickAction({ icon, label, onClick, variant = "default" }: QuickActionProps) {
  return (
    <Button
      variant={variant === "destructive" ? "destructive" : variant === "primary" ? "default" : "outline"}
      size="sm"
      className="flex-1"
      onClick={onClick}
    >
      {icon}
      <span className="ml-2">{label}</span>
    </Button>
  );
}

export function ContactSidebar({ className, onClose }: ContactSidebarProps) {
  const { selectedContact, timeline } = useContactStore();
  const isMobile = useIsMobile();

  if (!selectedContact) {
    return (
      <div className={cn("flex flex-col h-full items-center justify-center p-8", className)}>
        <p className="text-sm text-muted-foreground text-center">
          Select a contact to view details
        </p>
      </div>
    );
  }

  const displayName = [selectedContact.first_name, selectedContact.last_name].filter(Boolean).join(" ");
  const tags = selectedContact.tags?.split(",").map(t => t.trim()).filter(Boolean) ?? [];

  // Calculate some stats from timeline
  const callCount = timeline.filter(t => t.type === "call").length;
  const messageCount = timeline.filter(t => t.type === "sms").length;
  const lastActivity = timeline[timeline.length - 1];

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      className={cn("flex flex-col h-full bg-background", className)}
    >
      {/* Header with close button on mobile */}
      {isMobile && onClose && (
        <div className="flex items-center justify-between p-4 border-b">
          <h3 className="font-semibold">Contact Details</h3>
          <Button size="icon" variant="ghost" className="h-8 w-8" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      )}

      <ScrollArea className="flex-1">
        <div className="p-4 space-y-6">
          {/* Profile Section */}
          <div className="flex flex-col items-center text-center space-y-3">
            <Avatar className="h-20 w-20">
              <AvatarFallback className="bg-primary/10 text-primary text-2xl font-semibold">
                {getInitials(selectedContact)}
              </AvatarFallback>
            </Avatar>
            <div>
              <h2 className="text-xl font-semibold">{displayName || "Unknown"}</h2>
              {selectedContact.company_name && (
                <p className="text-sm text-muted-foreground">{selectedContact.company_name}</p>
              )}
            </div>
            <div className="flex items-center gap-2">
              <div className={cn("h-2 w-2 rounded-full", statusColors[selectedContact.status])} />
              <Badge variant="secondary" className="capitalize">
                {selectedContact.status}
              </Badge>
            </div>
          </div>

          <Separator />

          {/* Quick Actions */}
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-muted-foreground px-2">Quick Actions</h3>
            <div className="flex gap-2">
              <QuickAction
                icon={<Phone className="h-4 w-4" />}
                label="Call"
                onClick={() => console.log("Call")}
                variant="primary"
              />
              <QuickAction
                icon={<Calendar className="h-4 w-4" />}
                label="Schedule"
                onClick={() => console.log("Schedule")}
              />
            </div>
            <div className="flex gap-2">
              <QuickAction
                icon={<Edit2 className="h-4 w-4" />}
                label="Edit"
                onClick={() => console.log("Edit")}
              />
              <QuickAction
                icon={<Bot className="h-4 w-4" />}
                label="AI Engage"
                onClick={() => console.log("AI Engage")}
              />
            </div>
          </div>

          <Separator />

          {/* Contact Info */}
          <div className="space-y-1">
            <h3 className="text-sm font-medium text-muted-foreground px-2 mb-2">Contact Info</h3>
            <InfoRow
              icon={<Phone className="h-4 w-4 text-muted-foreground" />}
              label="Phone"
              value={selectedContact.phone_number}
              onClick={() => selectedContact.phone_number && window.open(`tel:${selectedContact.phone_number}`)}
            />
            <InfoRow
              icon={<Mail className="h-4 w-4 text-muted-foreground" />}
              label="Email"
              value={selectedContact.email}
              onClick={() => selectedContact.email && window.open(`mailto:${selectedContact.email}`)}
            />
            <InfoRow
              icon={<Building2 className="h-4 w-4 text-muted-foreground" />}
              label="Company"
              value={selectedContact.company_name}
            />
          </div>

          {/* Tags */}
          {tags.length > 0 && (
            <>
              <Separator />
              <div className="space-y-2">
                <h3 className="text-sm font-medium text-muted-foreground px-2">Tags</h3>
                <div className="flex flex-wrap gap-1.5 px-2">
                  {tags.map((tag) => (
                    <Badge key={tag} variant="secondary" className="text-xs">
                      {tag}
                    </Badge>
                  ))}
                </div>
              </div>
            </>
          )}

          {/* Activity Stats */}
          <Separator />
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-muted-foreground px-2">Activity</h3>
            <div className="grid grid-cols-2 gap-3 px-2">
              <div className="bg-muted/50 rounded-lg p-3 text-center">
                <p className="text-2xl font-semibold">{callCount}</p>
                <p className="text-xs text-muted-foreground">Calls</p>
              </div>
              <div className="bg-muted/50 rounded-lg p-3 text-center">
                <p className="text-2xl font-semibold">{messageCount}</p>
                <p className="text-xs text-muted-foreground">Messages</p>
              </div>
            </div>
            {lastActivity && (
              <div className="flex items-center gap-2 px-2 text-xs text-muted-foreground">
                <Clock className="h-3 w-3" />
                <span>
                  Last activity: {format(new Date(lastActivity.timestamp), "MMM d, h:mm a")}
                </span>
              </div>
            )}
          </div>

          {/* Notes */}
          {selectedContact.notes && (
            <>
              <Separator />
              <div className="space-y-2">
                <h3 className="text-sm font-medium text-muted-foreground px-2">Notes</h3>
                <div className="bg-muted/50 rounded-lg p-3">
                  <p className="text-sm whitespace-pre-wrap">{selectedContact.notes}</p>
                </div>
              </div>
            </>
          )}

          {/* Timestamps */}
          <Separator />
          <div className="space-y-1 px-2 text-xs text-muted-foreground">
            <p>Created: {format(new Date(selectedContact.created_at), "MMM d, yyyy 'at' h:mm a")}</p>
            <p>Updated: {format(new Date(selectedContact.updated_at), "MMM d, yyyy 'at' h:mm a")}</p>
          </div>
        </div>
      </ScrollArea>
    </motion.div>
  );
}
