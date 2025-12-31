"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { format, addDays, startOfWeek, addHours, isSameDay } from "date-fns";
import {
  ChevronLeft,
  ChevronRight,
  Plus,
  Calendar as CalendarIcon,
  Clock,
  User,
  MapPin,
  Video,
  ExternalLink,
  Settings,
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

// Mock appointments data
const mockAppointments = [
  {
    id: 1,
    title: "Property Viewing",
    contact: { name: "John Smith", initials: "JS" },
    date: addHours(new Date(), 2),
    duration: 60,
    type: "in_person",
    location: "123 Main Street",
    status: "confirmed",
  },
  {
    id: 2,
    title: "Follow-up Call",
    contact: { name: "Emily Johnson", initials: "EJ" },
    date: addHours(new Date(), 5),
    duration: 30,
    type: "video",
    meetingUrl: "https://meet.google.com/abc-defg-hij",
    status: "confirmed",
  },
  {
    id: 3,
    title: "Contract Discussion",
    contact: { name: "Michael Brown", initials: "MB" },
    date: addDays(new Date(), 1),
    duration: 45,
    type: "phone",
    status: "pending",
  },
  {
    id: 4,
    title: "Home Inspection",
    contact: { name: "Sarah Wilson", initials: "SW" },
    date: addDays(new Date(), 2),
    duration: 120,
    type: "in_person",
    location: "456 Oak Avenue",
    status: "confirmed",
  },
  {
    id: 5,
    title: "Initial Consultation",
    contact: { name: "David Lee", initials: "DL" },
    date: addDays(new Date(), 3),
    duration: 30,
    type: "video",
    meetingUrl: "https://meet.google.com/xyz-uvwx-rst",
    status: "confirmed",
  },
];

const statusColors: Record<string, string> = {
  confirmed: "bg-green-500/10 text-green-500 border-green-500/20",
  pending: "bg-yellow-500/10 text-yellow-500 border-yellow-500/20",
  cancelled: "bg-red-500/10 text-red-500 border-red-500/20",
};

const typeIcons: Record<string, React.ElementType> = {
  in_person: MapPin,
  video: Video,
  phone: Clock,
};

export function CalendarPage() {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [selectedAppointment, setSelectedAppointment] = useState<typeof mockAppointments[0] | null>(null);

  const weekStart = startOfWeek(currentDate, { weekStartsOn: 1 });
  const weekDays = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));

  const todayAppointments = mockAppointments.filter((apt) =>
    isSameDay(new Date(apt.date), new Date())
  );

  const upcomingAppointments = mockAppointments.filter(
    (apt) => new Date(apt.date) > new Date()
  );

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
                  const dayAppointments = mockAppointments.filter((apt) =>
                    isSameDay(new Date(apt.date), day)
                  );

                  return (
                    <div
                      key={day.toISOString()}
                      className="border rounded-lg p-2 min-h-[200px]"
                    >
                      <ScrollArea className="h-[180px]">
                        <div className="space-y-1">
                          {dayAppointments.map((apt) => (
                            <Dialog key={apt.id}>
                              <DialogTrigger asChild>
                                <motion.button
                                  className="w-full text-left p-2 rounded-md bg-primary/10 hover:bg-primary/20 transition-colors"
                                  whileHover={{ scale: 1.02 }}
                                  whileTap={{ scale: 0.98 }}
                                  onClick={() => setSelectedAppointment(apt)}
                                >
                                  <p className="text-xs font-medium truncate">
                                    {apt.title}
                                  </p>
                                  <p className="text-xs text-muted-foreground">
                                    {format(new Date(apt.date), "h:mm a")}
                                  </p>
                                </motion.button>
                              </DialogTrigger>
                              <DialogContent>
                                <DialogHeader>
                                  <DialogTitle>{apt.title}</DialogTitle>
                                  <DialogDescription>
                                    {format(
                                      new Date(apt.date),
                                      "EEEE, MMMM d, yyyy 'at' h:mm a"
                                    )}
                                  </DialogDescription>
                                </DialogHeader>
                                <div className="space-y-4 py-4">
                                  <div className="flex items-center gap-3">
                                    <Avatar className="size-10">
                                      <AvatarFallback>
                                        {apt.contact.initials}
                                      </AvatarFallback>
                                    </Avatar>
                                    <div>
                                      <p className="font-medium">
                                        {apt.contact.name}
                                      </p>
                                      <Badge
                                        variant="outline"
                                        className={statusColors[apt.status]}
                                      >
                                        {apt.status}
                                      </Badge>
                                    </div>
                                  </div>
                                  <div className="grid gap-2 text-sm">
                                    <div className="flex items-center gap-2">
                                      <Clock className="size-4 text-muted-foreground" />
                                      <span>{apt.duration} minutes</span>
                                    </div>
                                    {apt.location && (
                                      <div className="flex items-center gap-2">
                                        <MapPin className="size-4 text-muted-foreground" />
                                        <span>{apt.location}</span>
                                      </div>
                                    )}
                                    {apt.meetingUrl && (
                                      <div className="flex items-center gap-2">
                                        <Video className="size-4 text-muted-foreground" />
                                        <a
                                          href={apt.meetingUrl}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          className="text-primary hover:underline flex items-center gap-1"
                                        >
                                          Join Meeting
                                          <ExternalLink className="size-3" />
                                        </a>
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
                  {todayAppointments.map((apt) => {
                    const TypeIcon = typeIcons[apt.type];
                    return (
                      <div
                        key={apt.id}
                        className="flex items-center gap-3 p-2 rounded-lg border"
                      >
                        <Avatar className="size-8">
                          <AvatarFallback className="text-xs">
                            {apt.contact.initials}
                          </AvatarFallback>
                        </Avatar>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">
                            {apt.title}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {format(new Date(apt.date), "h:mm a")} •{" "}
                            {apt.duration}min
                          </p>
                        </div>
                        <TypeIcon className="size-4 text-muted-foreground" />
                      </div>
                    );
                  })}
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
                    className="flex items-center gap-3 p-2 rounded-lg hover:bg-muted/50 transition-colors"
                  >
                    <div className="text-center min-w-[40px]">
                      <div className="text-xs font-medium text-muted-foreground">
                        {format(new Date(apt.date), "MMM")}
                      </div>
                      <div className="text-lg font-bold">
                        {format(new Date(apt.date), "d")}
                      </div>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">
                        {apt.title}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {apt.contact.name} •{" "}
                        {format(new Date(apt.date), "h:mm a")}
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
                    {mockAppointments.length}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Total
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-muted/50">
                  <div className="text-2xl font-bold text-green-500">
                    {mockAppointments.filter((a) => a.status === "confirmed").length}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Confirmed
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
