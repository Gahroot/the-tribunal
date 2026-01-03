"use client";

import { useState, useMemo } from "react";
import { motion } from "framer-motion";
import { format, addDays, startOfWeek, isSameDay } from "date-fns";
import {
  ChevronLeft,
  ChevronRight,
  Plus,
  Calendar as CalendarIcon,
  Clock,
  Settings,
  Loader2,
  AlertCircle,
  Trash2,
} from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useAppointments, useDeleteAppointment } from "@/hooks/useAppointments";
import { useAuth } from "@/providers/auth-provider";
import { toast } from "sonner";
import type { Contact } from "@/types";

const statusColors: Record<string, string> = {
  scheduled: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  completed: "bg-green-500/10 text-green-500 border-green-500/20",
  cancelled: "bg-red-500/10 text-red-500 border-red-500/20",
  no_show: "bg-gray-500/10 text-gray-500 border-gray-500/20",
};

// Helper to get contact initials
function getInitials(firstName: string, lastName?: string): string {
  const first = firstName?.[0] ?? "";
  const last = lastName?.[0] ?? "";
  return (first + last).toUpperCase() || "?";
}

// Helper to get contact display name
function getContactName(contact: Contact | null | undefined): string {
  if (!contact) return "Unknown";
  return [contact.first_name, contact.last_name].filter(Boolean).join(" ");
}

export function CalendarPage() {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [selectedAppointmentId, setSelectedAppointmentId] = useState<number | null>(null);
  const { workspaceId } = useAuth();

  const { data: appointmentsData, isLoading, error } = useAppointments(
    workspaceId || "",
    { page: 1, page_size: 100 }
  );
  const deleteAppointmentMutation = useDeleteAppointment(workspaceId || "");

  const appointmentsList = useMemo(
    () => appointmentsData?.items || [],
    [appointmentsData?.items]
  );

  const weekStart = startOfWeek(currentDate, { weekStartsOn: 1 });
  const weekDays = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));

  const todayAppointments = useMemo(
    () =>
      appointmentsList.filter((apt) =>
        isSameDay(new Date(apt.scheduled_at), new Date())
      ),
    [appointmentsList]
  );

  const upcomingAppointments = useMemo(
    () =>
      appointmentsList.filter(
        (apt) => new Date(apt.scheduled_at) > new Date()
      ),
    [appointmentsList]
  );

  const handleDeleteAppointment = async (appointmentId: number) => {
    deleteAppointmentMutation.mutate(appointmentId, {
      onSuccess: () => {
        toast.success("Appointment cancelled");
        setSelectedAppointmentId(null);
      },
      onError: () => {
        toast.error("Failed to cancel appointment");
      },
    });
  };

  if (isLoading) {
    return (
      <div className="p-6 flex items-center justify-center h-96">
        <Loader2 className="size-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6 flex flex-col items-center justify-center h-96 gap-2">
        <AlertCircle className="size-8 text-destructive" />
        <p className="text-muted-foreground">Failed to load appointments</p>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Calendar</h1>
          <p className="text-muted-foreground">
            Manage appointments and scheduling
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" asChild>
            <Link href="/settings">
              <Settings className="mr-2 size-4" />
              Cal.com Settings
            </Link>
          </Button>
          <Button>
            <Plus className="mr-2 size-4" />
            New Appointment
          </Button>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Calendar View */}
        <div className="lg:col-span-2 space-y-4">
          {/* Week Navigation */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg">
                  {format(weekStart, "MMMM yyyy")}
                </CardTitle>
                <div className="flex items-center gap-1">
                  <Button
                    variant="outline"
                    size="icon-sm"
                    onClick={() => setCurrentDate(addDays(currentDate, -7))}
                  >
                    <ChevronLeft className="size-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentDate(new Date())}
                  >
                    Today
                  </Button>
                  <Button
                    variant="outline"
                    size="icon-sm"
                    onClick={() => setCurrentDate(addDays(currentDate, 7))}
                  >
                    <ChevronRight className="size-4" />
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {/* Week Days Header */}
              <div className="grid grid-cols-7 gap-2 mb-2">
                {weekDays.map((day) => (
                  <div
                    key={day.toISOString()}
                    className={`text-center p-2 rounded-lg ${
                      isSameDay(day, new Date())
                        ? "bg-primary text-primary-foreground"
                        : ""
                    }`}
                  >
                    <div className="text-xs font-medium">
                      {format(day, "EEE")}
                    </div>
                    <div className="text-lg font-bold">{format(day, "d")}</div>
                  </div>
                ))}
              </div>

              {/* Appointments for the week */}
              <div className="grid grid-cols-7 gap-2 min-h-[300px]">
                {weekDays.map((day) => {
                  const dayAppointments = appointmentsList.filter((apt) =>
                    isSameDay(new Date(apt.scheduled_at), day)
                  );

                  return (
                    <div
                      key={day.toISOString()}
                      className="border rounded-lg p-2 min-h-[200px]"
                    >
                      <ScrollArea className="h-[180px]">
                        <div className="space-y-1">
                          {dayAppointments.map((apt) => (
                            <Dialog key={apt.id} open={selectedAppointmentId === apt.id} onOpenChange={(open) => !open && setSelectedAppointmentId(null)}>
                              <DialogTrigger asChild>
                                <motion.button
                                  className="w-full text-left p-2 rounded-md bg-primary/10 hover:bg-primary/20 transition-colors"
                                  whileHover={{ scale: 1.02 }}
                                  whileTap={{ scale: 0.98 }}
                                  onClick={() => setSelectedAppointmentId(apt.id)}
                                >
                                  <p className="text-xs font-medium truncate">
                                    {apt.service_type || "Appointment"}
                                  </p>
                                  <p className="text-xs text-muted-foreground">
                                    {format(new Date(apt.scheduled_at), "h:mm a")}
                                  </p>
                                </motion.button>
                              </DialogTrigger>
                              <DialogContent>
                                <DialogHeader>
                                  <DialogTitle>{apt.service_type || "Appointment"}</DialogTitle>
                                  <DialogDescription>
                                    {format(
                                      new Date(apt.scheduled_at),
                                      "EEEE, MMMM d, yyyy 'at' h:mm a"
                                    )}
                                  </DialogDescription>
                                </DialogHeader>
                                <div className="space-y-4 py-4">
                                  <div className="flex items-start justify-between gap-3">
                                    <div className="flex items-center gap-3">
                                      <Avatar className="size-10">
                                        <AvatarFallback>
                                          {getInitials(apt.contact?.first_name || "", apt.contact?.last_name)}
                                        </AvatarFallback>
                                      </Avatar>
                                      <div>
                                        <p className="font-medium">
                                          {getContactName(apt.contact)}
                                        </p>
                                        <Badge
                                          variant="outline"
                                          className={statusColors[apt.status]}
                                        >
                                          {apt.status}
                                        </Badge>
                                      </div>
                                    </div>
                                    {apt.status === "scheduled" && (
                                      <Button
                                        variant="ghost"
                                        size="icon"
                                        onClick={() => handleDeleteAppointment(apt.id)}
                                        disabled={deleteAppointmentMutation.isPending}
                                        className="text-destructive hover:text-destructive"
                                      >
                                        <Trash2 className="size-4" />
                                      </Button>
                                    )}
                                  </div>
                                  <div className="grid gap-2 text-sm">
                                    <div className="flex items-center gap-2">
                                      <Clock className="size-4 text-muted-foreground" />
                                      <span>{apt.duration_minutes} minutes</span>
                                    </div>
                                    {apt.notes && (
                                      <div className="text-sm text-muted-foreground">
                                        {apt.notes}
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </DialogContent>
                            </Dialog>
                          ))}
                        </div>
                      </ScrollArea>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {/* Today's Schedule */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CalendarIcon className="size-5" />
                Today
              </CardTitle>
              <CardDescription>
                {format(new Date(), "EEEE, MMMM d")}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {todayAppointments.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">
                  No appointments today
                </p>
              ) : (
                <div className="space-y-3">
                  {todayAppointments.map((apt) => (
                    <div
                      key={apt.id}
                      className="flex items-center gap-3 p-2 rounded-lg border hover:bg-muted/50 transition-colors cursor-pointer"
                      onClick={() => setSelectedAppointmentId(apt.id)}
                    >
                      <Avatar className="size-8">
                        <AvatarFallback className="text-xs">
                          {getInitials(apt.contact?.first_name || "", apt.contact?.last_name)}
                        </AvatarFallback>
                      </Avatar>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">
                          {getContactName(apt.contact)}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {format(new Date(apt.scheduled_at), "h:mm a")} • {apt.duration_minutes}min
                        </p>
                      </div>
                      <Badge
                        variant="outline"
                        className={statusColors[apt.status]}
                      >
                        {apt.status}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Upcoming */}
          <Card>
            <CardHeader>
              <CardTitle>Upcoming</CardTitle>
              <CardDescription>Next 7 days</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {upcomingAppointments.slice(0, 5).map((apt) => (
                  <div
                    key={apt.id}
                    className="flex items-center gap-3 p-2 rounded-lg hover:bg-muted/50 transition-colors cursor-pointer"
                    onClick={() => setSelectedAppointmentId(apt.id)}
                  >
                    <div className="text-center min-w-[40px]">
                      <div className="text-xs font-medium text-muted-foreground">
                        {format(new Date(apt.scheduled_at), "MMM")}
                      </div>
                      <div className="text-lg font-bold">
                        {format(new Date(apt.scheduled_at), "d")}
                      </div>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">
                        {getContactName(apt.contact)}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {apt.service_type || "Appointment"} • {format(new Date(apt.scheduled_at), "h:mm a")}
                      </p>
                    </div>
                    <Badge
                      variant="outline"
                      className={statusColors[apt.status]}
                    >
                      {apt.status}
                    </Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Quick Stats */}
          <Card>
            <CardHeader>
              <CardTitle>This Week</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4 text-center">
                <div className="p-3 rounded-lg bg-muted/50">
                  <div className="text-2xl font-bold">
                    {appointmentsList.length}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Total
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-muted/50">
                  <div className="text-2xl font-bold text-green-500">
                    {appointmentsList.filter((a) => a.status === "scheduled").length}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Scheduled
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
