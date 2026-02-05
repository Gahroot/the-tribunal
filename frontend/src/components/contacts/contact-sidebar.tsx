"use client";

import * as React from "react";
import { useState } from "react";
import { format } from "date-fns";
import {
  Phone,
  Mail,
  Building2,
  Calendar,
  Clock,
  ChevronRight,
  Edit2,
  Bot,
  X,
  Loader2,
  Trash2,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";
import { useContactStore } from "@/lib/contact-store";
import { useIsMobile } from "@/hooks/use-mobile";
import { useAppointments } from "@/hooks/useAppointments";
import { useToggleContactAI, useDeleteContact } from "@/hooks/useContacts";
import { useWorkspaceId } from "@/hooks/use-workspace-id";
import { callsApi, type InitiateCallRequest } from "@/lib/api/calls";
import { conversationsApi } from "@/lib/api/conversations";
import { phoneNumbersApi } from "@/lib/api/phone-numbers";
import { EditContactDialog } from "@/components/contacts/edit-contact-dialog";
import { ScheduleAppointmentDialog } from "@/components/contacts/schedule-appointment-dialog";
import { TagBadge } from "@/components/tags/tag-badge";
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
  loading?: boolean;
  disabled?: boolean;
}

function QuickAction({
  icon,
  label,
  onClick,
  variant = "default",
  loading = false,
  disabled = false,
}: QuickActionProps) {
  return (
    <Button
      variant={variant === "destructive" ? "destructive" : variant === "primary" ? "default" : "outline"}
      size="sm"
      className="flex-1"
      onClick={onClick}
      disabled={disabled || loading}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : icon}
      <span className="ml-2">{label}</span>
    </Button>
  );
}

export function ContactSidebar({ className, onClose }: ContactSidebarProps) {
  const router = useRouter();
  const { selectedContact, setSelectedContact, timeline } = useContactStore();
  const isMobile = useIsMobile();
  const workspaceId = useWorkspaceId();

  // Dialog states
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [scheduleDialogOpen, setScheduleDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);

  // Fetch appointments for this contact
  const { data: appointmentsData, isLoading: appointmentsLoading } = useAppointments(
    workspaceId ?? "",
    { page: 1, page_size: 50 }
  );

  // Fetch phone numbers for calls
  const { data: phoneNumbersData } = useQuery({
    queryKey: ["phone-numbers", workspaceId],
    queryFn: () =>
      workspaceId
        ? phoneNumbersApi.list(workspaceId, { active_only: true })
        : Promise.resolve({ items: [], total: 0, page: 1, page_size: 50, pages: 0 }),
    enabled: !!workspaceId,
  });

  // AI toggle state - track locally for UI responsiveness
  const [aiEnabled, setAiEnabled] = useState(false);

  // Fetch conversations for this contact to get AI state
  const { data: conversationsData } = useQuery({
    queryKey: ["conversations", workspaceId, selectedContact?.id],
    queryFn: () =>
      workspaceId
        ? conversationsApi.list(workspaceId, { page: 1, page_size: 100 })
        : Promise.resolve({ items: [], total: 0, page: 1, page_size: 100, pages: 0 }),
    enabled: !!workspaceId && !!selectedContact,
  });

  // Find conversation for current contact to get AI state
  const contactConversation = conversationsData?.items?.find(
    (conv) => conv.contact_id === selectedContact?.id
  );

  // Sync AI state from conversation
  React.useEffect(() => {
    if (contactConversation) {
      setAiEnabled(contactConversation.ai_enabled);
    }
  }, [contactConversation]);

  // Initiate call mutation
  const initiateCallMutation = useMutation({
    mutationFn: (data: InitiateCallRequest) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return callsApi.initiate(workspaceId, data);
    },
    onSuccess: () => {
      toast.success("Call initiated successfully!");
    },
    onError: (error) => {
      console.error("Failed to initiate call:", error);
      toast.error("Failed to initiate call. Please try again.");
    },
  });

  // AI toggle mutation - uses the new contact-based endpoint
  const toggleAIMutation = useToggleContactAI(workspaceId ?? "");

  // Delete contact mutation
  const deleteContactMutation = useDeleteContact(workspaceId ?? "");

  // Handle call action
  const handleCall = () => {
    if (!selectedContact?.phone_number) {
      toast.error("Contact has no phone number");
      return;
    }

    const voiceEnabledNumbers = phoneNumbersData?.items?.filter((p) => p.voice_enabled) || [];
    if (voiceEnabledNumbers.length === 0) {
      toast.error("No voice-enabled phone numbers available");
      return;
    }

    // Use the first available voice-enabled number
    const fromNumber = voiceEnabledNumbers[0].phone_number;

    initiateCallMutation.mutate({
      to_number: selectedContact.phone_number,
      from_phone_number: fromNumber,
      contact_phone: selectedContact.phone_number,
    });
  };

  // Handle AI engage action
  const handleAIEngage = () => {
    if (!selectedContact) return;

    // Toggle AI - if currently enabled, disable it, and vice versa
    const newState = !aiEnabled;

    // Optimistically update UI
    setAiEnabled(newState);

    toggleAIMutation.mutate(
      {
        contactId: selectedContact.id,
        enabled: newState,
      },
      {
        onSuccess: (data) => {
          toast.success(data.ai_enabled ? "AI engagement enabled!" : "AI engagement disabled!");
        },
        onError: (error) => {
          // Revert on error
          setAiEnabled(!newState);
          console.error("Failed to toggle AI:", error);
          toast.error("Failed to toggle AI engagement. Please try again.");
        },
      }
    );
  };

  // Handle delete action
  const handleDelete = () => {
    if (!selectedContact) return;

    deleteContactMutation.mutate(selectedContact.id, {
      onSuccess: () => {
        toast.success("Contact deleted successfully");
        setSelectedContact(null);
        setDeleteDialogOpen(false);
        router.push("/contacts");
      },
      onError: (error) => {
        console.error("Failed to delete contact:", error);
        toast.error("Failed to delete contact. Please try again.");
      },
    });
  };

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
  const tags = Array.isArray(selectedContact.tags)
    ? selectedContact.tags
    : typeof selectedContact.tags === "string"
      ? selectedContact.tags.split(",").map((t) => t.trim()).filter(Boolean)
      : [];

  // Filter appointments for this contact
  const contactAppointments = (appointmentsData?.items || []).filter(
    (apt) => apt.contact_id === selectedContact.id
  );

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
                onClick={handleCall}
                variant="primary"
                loading={initiateCallMutation.isPending}
                disabled={!selectedContact.phone_number}
              />
              <QuickAction
                icon={<Calendar className="h-4 w-4" />}
                label="Schedule"
                onClick={() => setScheduleDialogOpen(true)}
              />
            </div>
            <div className="flex gap-2">
              <QuickAction
                icon={<Edit2 className="h-4 w-4" />}
                label="Edit"
                onClick={() => setEditDialogOpen(true)}
              />
              <QuickAction
                icon={<Bot className="h-4 w-4" />}
                label={aiEnabled ? "AI On" : "AI Off"}
                onClick={handleAIEngage}
                loading={toggleAIMutation.isPending}
                variant={aiEnabled ? "primary" : "default"}
              />
            </div>
            <div className="flex gap-2">
              <QuickAction
                icon={<Trash2 className="h-4 w-4" />}
                label="Delete"
                onClick={() => setDeleteDialogOpen(true)}
                variant="destructive"
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
          {(selectedContact.tag_objects && selectedContact.tag_objects.length > 0) ? (
            <>
              <Separator />
              <div className="space-y-2">
                <h3 className="text-sm font-medium text-muted-foreground px-2">Tags</h3>
                <div className="flex flex-wrap gap-1.5 px-2">
                  {selectedContact.tag_objects.map((tag) => (
                    <TagBadge key={tag.id} name={tag.name} color={tag.color} />
                  ))}
                </div>
              </div>
            </>
          ) : tags.length > 0 ? (
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
          ) : null}

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

          {/* Appointments */}
          <Separator />
          <div className="space-y-2">
            <h3 className="text-sm font-medium text-muted-foreground px-2">Appointments</h3>
            {appointmentsLoading ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            ) : contactAppointments.length === 0 ? (
              <p className="text-xs text-muted-foreground px-2 py-2">No appointments scheduled</p>
            ) : (
              <div className="space-y-2 px-2">
                {contactAppointments.slice(0, 3).map((apt) => (
                  <div
                    key={apt.id}
                    className="flex items-center gap-2 p-2 rounded-lg bg-muted/30 text-xs"
                  >
                    <Calendar className="h-3 w-3 text-muted-foreground shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="font-medium truncate">
                        {apt.service_type || "Appointment"}
                      </p>
                      <p className="text-muted-foreground text-xs">
                        {format(new Date(apt.scheduled_at), "MMM d, h:mm a")}
                      </p>
                    </div>
                    <Badge
                      variant="outline"
                      className="text-xs py-0"
                    >
                      {apt.status}
                    </Badge>
                  </div>
                ))}
                {contactAppointments.length > 3 && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full text-xs"
                    asChild
                  >
                    <a href="/calendar">
                      View all ({contactAppointments.length})
                    </a>
                  </Button>
                )}
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

      {/* Dialogs */}
      <EditContactDialog
        contact={selectedContact}
        open={editDialogOpen}
        onOpenChange={setEditDialogOpen}
      />
      <ScheduleAppointmentDialog
        contact={selectedContact}
        open={scheduleDialogOpen}
        onOpenChange={setScheduleDialogOpen}
      />

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Contact</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete {displayName || "this contact"}? This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={deleteContactMutation.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteContactMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  Deleting...
                </>
              ) : (
                "Delete"
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </motion.div>
  );
}
