"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { format, formatDistanceToNow } from "date-fns";
import { useQuery } from "@tanstack/react-query";
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
  Loader2,
  AlertCircle,
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
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { TranscriptViewer } from "@/components/calls/transcript-viewer";
import { useWorkspaceId } from "@/hooks/use-workspace-id";
import { callsApi } from "@/lib/api/calls";

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

function getInitials(phoneNumber: string | undefined | null): string {
  if (!phoneNumber) return "??";
  // Get last 2 digits of phone number as initials
  const digits = phoneNumber.replace(/\D/g, "");
  return digits.slice(-2) || "??";
}

export function CallsList() {
  const [searchQuery, setSearchQuery] = useState("");
  const [directionFilter, setDirectionFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const workspaceId = useWorkspaceId();

  const { data: callsData, isLoading, error } = useQuery({
    queryKey: ["calls", workspaceId, page, directionFilter, statusFilter],
    queryFn: () => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return callsApi.list(workspaceId, {
        page,
        page_size: pageSize,
        direction: directionFilter !== "all" ? directionFilter as "inbound" | "outbound" : undefined,
        status: statusFilter !== "all" ? statusFilter : undefined,
      });
    },
    enabled: !!workspaceId,
  });

  const calls = callsData?.items ?? [];
  const totalCalls = callsData?.total ?? 0;
  const totalPages = callsData?.pages ?? 1;

  // Client-side search filter (API filtering is by direction/status, search is client-side)
  const filteredCalls = calls.filter((call) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    const fromNumber = call.from_number?.toLowerCase() || "";
    const toNumber = call.to_number?.toLowerCase() || "";
    return fromNumber.includes(query) || toNumber.includes(query);
  });

  // Calculate stats from current page data
  const completedCalls = calls.filter((c) => c.status === "completed").length;
  const totalDuration = calls.reduce((sum, c) => sum + (c.duration_seconds || 0), 0);
  const avgDuration = completedCalls > 0 ? Math.round(totalDuration / completedCalls) : 0;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="size-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-4">
        <AlertCircle className="size-12 text-destructive" />
        <p className="text-muted-foreground">Failed to load calls</p>
        <p className="text-sm text-muted-foreground">{(error as Error).message}</p>
      </div>
    );
  }

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
          { label: "Completed (page)", value: completedCalls, icon: Phone },
          { label: "Total Duration (page)", value: formatDuration(totalDuration), icon: Clock },
          { label: "Avg Duration (page)", value: formatDuration(avgDuration), icon: Clock },
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
                placeholder="Search by phone number..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
              />
            </div>
            <div className="flex gap-2">
              <Select value={directionFilter} onValueChange={(v) => { setDirectionFilter(v); setPage(1); }}>
                <SelectTrigger className="w-[140px]">
                  <SelectValue placeholder="Direction" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Directions</SelectItem>
                  <SelectItem value="inbound">Inbound</SelectItem>
                  <SelectItem value="outbound">Outbound</SelectItem>
                </SelectContent>
              </Select>
              <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(1); }}>
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
          {filteredCalls.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12">
              <Phone className="size-12 text-muted-foreground/50 mb-4" />
              <p className="text-muted-foreground">No calls found</p>
              <p className="text-sm text-muted-foreground">
                Voice calls will appear here once made
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Phone Number</TableHead>
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
                    const status = statusConfig[call.status] || statusConfig.completed;
                    const DirectionIcon =
                      call.direction === "inbound" ? PhoneIncoming : PhoneOutgoing;
                    const displayNumber = (call.direction === "inbound" ? call.from_number : call.to_number) || "Unknown";

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
                                {getInitials(displayNumber)}
                              </AvatarFallback>
                            </Avatar>
                            <div>
                              <div className="font-medium font-mono text-sm">
                                {displayNumber}
                              </div>
                              <div className="text-xs text-muted-foreground">
                                {call.direction === "inbound" ? "From" : "To"}
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
                          {call.is_ai || call.agent_id ? (
                            <div className="flex items-center gap-2">
                              <Bot className="size-4 text-primary" />
                              <span className="text-sm">{call.agent_name || "AI Agent"}</span>
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
                            {formatDistanceToNow(new Date(call.created_at), {
                              addSuffix: true,
                            })}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {format(new Date(call.created_at), "MMM d, h:mm a")}
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
                                >
                                  View
                                </Button>
                              </DialogTrigger>
                              <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                                <DialogHeader>
                                  <DialogTitle>Call Details</DialogTitle>
                                  <DialogDescription>
                                    {displayNumber} -{" "}
                                    {format(
                                      new Date(call.created_at),
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
                                      {call.is_ai || call.agent_id ? (call.agent_name || "AI Agent") : "Manual"}
                                    </div>
                                    <div>
                                      <span className="text-muted-foreground">
                                        From:
                                      </span>{" "}
                                      <span className="font-mono">{call.from_number || "N/A"}</span>
                                    </div>
                                    <div>
                                      <span className="text-muted-foreground">
                                        To:
                                      </span>{" "}
                                      <span className="font-mono">{call.to_number || "N/A"}</span>
                                    </div>
                                  </div>
                                  {call.transcript && (
                                    <div className="space-y-2">
                                      <h4 className="font-medium">Transcript</h4>
                                      <TranscriptViewer
                                        transcript={call.transcript}
                                        maxHeight="400px"
                                      />
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
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted-foreground">
          Page {page} of {totalPages} ({totalCalls} total calls)
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage(p => Math.max(1, p - 1))}
          >
            <ChevronLeft className="size-4" />
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage(p => p + 1)}
          >
            Next
            <ChevronRight className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
