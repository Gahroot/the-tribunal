"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { format, formatDistanceToNow } from "date-fns";
import {
  Search,
  Phone,
  PhoneIncoming,
  PhoneOutgoing,
  PhoneMissed,
  Play,
  Clock,
  User,
  Bot,
  Download,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import type { CallRecord } from "@/types";

// Mock data
const mockCalls: CallRecord[] = [
  {
    id: "call-1",
    user_id: "1",
    contact_id: 1,
    agent_id: "agent-1",
    direction: "outbound",
    status: "completed",
    from_number: "+1234567890",
    to_number: "+1987654321",
    duration_seconds: 245,
    recording_url: "https://example.com/recording1.mp3",
    transcript: "Agent: Hello, this is Sarah from Real Estate Co...\nContact: Hi, yes I was interested in the property...",
    started_at: "2024-01-20T14:30:00Z",
    answered_at: "2024-01-20T14:30:15Z",
    ended_at: "2024-01-20T14:34:20Z",
    created_at: "2024-01-20T14:30:00Z",
  },
  {
    id: "call-2",
    user_id: "1",
    contact_id: 2,
    direction: "inbound",
    status: "completed",
    from_number: "+1555123456",
    to_number: "+1234567890",
    duration_seconds: 180,
    transcript: "Contact: Hi, I'm calling about the listing on Main Street...",
    started_at: "2024-01-20T12:15:00Z",
    answered_at: "2024-01-20T12:15:05Z",
    ended_at: "2024-01-20T12:18:05Z",
    created_at: "2024-01-20T12:15:00Z",
  },
  {
    id: "call-3",
    user_id: "1",
    contact_id: 3,
    agent_id: "agent-2",
    direction: "outbound",
    status: "no_answer",
    from_number: "+1234567890",
    to_number: "+1666789012",
    started_at: "2024-01-20T10:00:00Z",
    created_at: "2024-01-20T10:00:00Z",
  },
  {
    id: "call-4",
    user_id: "1",
    contact_id: 4,
    agent_id: "agent-1",
    direction: "outbound",
    status: "completed",
    from_number: "+1234567890",
    to_number: "+1777890123",
    duration_seconds: 420,
    recording_url: "https://example.com/recording4.mp3",
    transcript: "Agent: Good afternoon, this is an AI assistant calling on behalf of...",
    started_at: "2024-01-19T16:45:00Z",
    answered_at: "2024-01-19T16:45:20Z",
    ended_at: "2024-01-19T16:52:20Z",
    created_at: "2024-01-19T16:45:00Z",
  },
  {
    id: "call-5",
    user_id: "1",
    contact_id: 5,
    direction: "inbound",
    status: "completed",
    from_number: "+1888901234",
    to_number: "+1234567890",
    duration_seconds: 95,
    started_at: "2024-01-19T11:30:00Z",
    answered_at: "2024-01-19T11:30:10Z",
    ended_at: "2024-01-19T11:31:45Z",
    created_at: "2024-01-19T11:30:00Z",
  },
];

const mockContacts: Record<number, { name: string; initials: string }> = {
  1: { name: "John Smith", initials: "JS" },
  2: { name: "Emily Johnson", initials: "EJ" },
  3: { name: "Michael Brown", initials: "MB" },
  4: { name: "Sarah Wilson", initials: "SW" },
  5: { name: "David Lee", initials: "DL" },
};

const mockAgents: Record<string, string> = {
  "agent-1": "Sarah - Sales Agent",
  "agent-2": "Mike - Support Agent",
};

const statusConfig: Record<string, { label: string; color: string; icon: React.ElementType }> = {
  completed: { label: "Completed", color: "bg-green-500/10 text-green-500 border-green-500/20", icon: Phone },
  in_progress: { label: "In Progress", color: "bg-blue-500/10 text-blue-500 border-blue-500/20", icon: Phone },
  initiated: { label: "Initiated", color: "bg-blue-500/10 text-blue-500 border-blue-500/20", icon: Phone },
  ringing: { label: "Ringing", color: "bg-yellow-500/10 text-yellow-500 border-yellow-500/20", icon: Phone },
  no_answer: { label: "No Answer", color: "bg-gray-500/10 text-gray-500 border-gray-500/20", icon: PhoneMissed },
  busy: { label: "Busy", color: "bg-orange-500/10 text-orange-500 border-orange-500/20", icon: PhoneMissed },
  failed: { label: "Failed", color: "bg-red-500/10 text-red-500 border-red-500/20", icon: PhoneMissed },
};

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export function CallsList() {
  const [searchQuery, setSearchQuery] = useState("");
  const [directionFilter, setDirectionFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const [selectedCall, setSelectedCall] = useState<CallRecord | null>(null);

  const filteredCalls = mockCalls.filter((call) => {
    const contact = mockContacts[call.contact_id || 0];
    const matchesSearch = contact?.name
      .toLowerCase()
      .includes(searchQuery.toLowerCase()) ||
      call.from_number.includes(searchQuery) ||
      call.to_number.includes(searchQuery);
    const matchesDirection =
      directionFilter === "all" || call.direction === directionFilter;
    const matchesStatus =
      statusFilter === "all" || call.status === statusFilter;
    return matchesSearch && matchesDirection && matchesStatus;
  });

  // Stats
  const totalCalls = mockCalls.length;
  const completedCalls = mockCalls.filter((c) => c.status === "completed").length;
  const totalDuration = mockCalls.reduce((sum, c) => sum + (c.duration_seconds || 0), 0);
  const avgDuration = completedCalls > 0 ? Math.round(totalDuration / completedCalls) : 0;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Calls</h1>
          <p className="text-muted-foreground">
            View and manage all voice calls
          </p>
        </div>
        <Button variant="outline">
          <Download className="mr-2 size-4" />
          Export
        </Button>
      </div>

      {/* Stats Cards */}
      <motion.div
        className="grid gap-4 md:grid-cols-4"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ staggerChildren: 0.1 }}
      >
        {[
          { label: "Total Calls", value: totalCalls, icon: Phone },
          { label: "Completed", value: completedCalls, icon: Phone },
          { label: "Total Duration", value: formatDuration(totalDuration), icon: Clock },
          { label: "Avg Duration", value: formatDuration(avgDuration), icon: Clock },
        ].map((stat) => (
          <Card key={stat.label}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardDescription>{stat.label}</CardDescription>
              <stat.icon className="size-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stat.value}</div>
            </CardContent>
          </Card>
        ))}
      </motion.div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search by contact or phone number..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
              />
            </div>
            <div className="flex gap-2">
              <Select value={directionFilter} onValueChange={setDirectionFilter}>
                <SelectTrigger className="w-[140px]">
                  <SelectValue placeholder="Direction" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Directions</SelectItem>
                  <SelectItem value="inbound">Inbound</SelectItem>
                  <SelectItem value="outbound">Outbound</SelectItem>
                </SelectContent>
              </Select>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-[140px]">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="completed">Completed</SelectItem>
                  <SelectItem value="no_answer">No Answer</SelectItem>
                  <SelectItem value="busy">Busy</SelectItem>
                  <SelectItem value="failed">Failed</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Calls Table */}
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Contact</TableHead>
                <TableHead>Direction</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>Agent</TableHead>
                <TableHead>Time</TableHead>
                <TableHead className="w-[100px]">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <AnimatePresence mode="popLayout">
                {filteredCalls.map((call) => {
                  const contact = mockContacts[call.contact_id || 0];
                  const status = statusConfig[call.status];
                  const DirectionIcon =
                    call.direction === "inbound" ? PhoneIncoming : PhoneOutgoing;

                  return (
                    <motion.tr
                      key={call.id}
                      layout
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="group"
                    >
                      <TableCell>
                        <div className="flex items-center gap-3">
                          <Avatar className="size-8">
                            <AvatarFallback className="text-xs">
                              {contact?.initials || "?"}
                            </AvatarFallback>
                          </Avatar>
                          <div>
                            <div className="font-medium">
                              {contact?.name || "Unknown"}
                            </div>
                            <div className="text-xs text-muted-foreground">
                              {call.direction === "inbound"
                                ? call.from_number
                                : call.to_number}
                            </div>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <DirectionIcon
                            className={`size-4 ${
                              call.direction === "inbound"
                                ? "text-blue-500"
                                : "text-green-500"
                            }`}
                          />
                          <span className="capitalize">{call.direction}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={status.color}>
                          {status.label}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {call.duration_seconds
                          ? formatDuration(call.duration_seconds)
                          : "-"}
                      </TableCell>
                      <TableCell>
                        {call.agent_id ? (
                          <div className="flex items-center gap-2">
                            <Bot className="size-4 text-primary" />
                            <span className="text-sm">
                              {mockAgents[call.agent_id] || "AI Agent"}
                            </span>
                          </div>
                        ) : (
                          <div className="flex items-center gap-2">
                            <User className="size-4 text-muted-foreground" />
                            <span className="text-sm text-muted-foreground">
                              Manual
                            </span>
                          </div>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="text-sm">
                          {formatDistanceToNow(new Date(call.started_at), {
                            addSuffix: true,
                          })}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {format(new Date(call.started_at), "MMM d, h:mm a")}
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1">
                          {call.recording_url && (
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              className="opacity-0 group-hover:opacity-100"
                            >
                              <Play className="size-4" />
                            </Button>
                          )}
                          <Dialog>
                            <DialogTrigger asChild>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="opacity-0 group-hover:opacity-100"
                                onClick={() => setSelectedCall(call)}
                              >
                                View
                              </Button>
                            </DialogTrigger>
                            <DialogContent className="max-w-2xl">
                              <DialogHeader>
                                <DialogTitle>Call Details</DialogTitle>
                                <DialogDescription>
                                  {contact?.name} -{" "}
                                  {format(
                                    new Date(call.started_at),
                                    "MMMM d, yyyy 'at' h:mm a"
                                  )}
                                </DialogDescription>
                              </DialogHeader>
                              <div className="space-y-4">
                                <div className="grid grid-cols-2 gap-4 text-sm">
                                  <div>
                                    <span className="text-muted-foreground">
                                      Direction:
                                    </span>{" "}
                                    <span className="capitalize">
                                      {call.direction}
                                    </span>
                                  </div>
                                  <div>
                                    <span className="text-muted-foreground">
                                      Status:
                                    </span>{" "}
                                    {status.label}
                                  </div>
                                  <div>
                                    <span className="text-muted-foreground">
                                      Duration:
                                    </span>{" "}
                                    {call.duration_seconds
                                      ? formatDuration(call.duration_seconds)
                                      : "-"}
                                  </div>
                                  <div>
                                    <span className="text-muted-foreground">
                                      Agent:
                                    </span>{" "}
                                    {call.agent_id
                                      ? mockAgents[call.agent_id]
                                      : "Manual"}
                                  </div>
                                </div>
                                {call.transcript && (
                                  <div className="space-y-2">
                                    <h4 className="font-medium">Transcript</h4>
                                    <ScrollArea className="h-[200px] rounded-md border p-4">
                                      <pre className="text-sm whitespace-pre-wrap">
                                        {call.transcript}
                                      </pre>
                                    </ScrollArea>
                                  </div>
                                )}
                                {call.recording_url && (
                                  <div className="space-y-2">
                                    <h4 className="font-medium">Recording</h4>
                                    <audio controls className="w-full">
                                      <source
                                        src={call.recording_url}
                                        type="audio/mpeg"
                                      />
                                    </audio>
                                  </div>
                                )}
                              </div>
                            </DialogContent>
                          </Dialog>
                        </div>
                      </TableCell>
                    </motion.tr>
                  );
                })}
              </AnimatePresence>
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted-foreground">
          Showing {filteredCalls.length} of {mockCalls.length} calls
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" disabled>
            <ChevronLeft className="size-4" />
            Previous
          </Button>
          <Button variant="outline" size="sm" disabled>
            Next
            <ChevronRight className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
