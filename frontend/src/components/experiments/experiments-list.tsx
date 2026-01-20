"use client";

import { useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Search,
  MoreHorizontal,
  Play,
  Pause,
  Trash2,
  ChevronLeft,
  ChevronRight,
  Loader2,
  AlertCircle,
  FlaskConical,
  Trophy,
  CheckCircle2,
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import { Progress } from "@/components/ui/progress";
import { useWorkspaceId } from "@/hooks/use-workspace-id";
import type { MessageTest, MessageTestStatus } from "@/types";
import { messageTestsApi } from "@/lib/api/message-tests";

const statusColors: Record<MessageTestStatus, string> = {
  draft: "bg-gray-500/10 text-gray-500 border-gray-500/20",
  running: "bg-green-500/10 text-green-500 border-green-500/20",
  paused: "bg-yellow-500/10 text-yellow-500 border-yellow-500/20",
  completed: "bg-purple-500/10 text-purple-500 border-purple-500/20",
};

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.05 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 },
};

export function ExperimentsList() {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const workspaceId = useWorkspaceId();

  const queryClient = useQueryClient();

  const { data: testsData, isLoading, error } = useQuery({
    queryKey: ["message-tests", workspaceId],
    queryFn: () => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return messageTestsApi.list(workspaceId);
    },
    enabled: !!workspaceId,
  });

  const tests = testsData?.items ?? [];

  const pauseMutation = useMutation({
    mutationFn: (id: string) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return messageTestsApi.pause(workspaceId, id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["message-tests", workspaceId] });
      toast.success("Test paused");
    },
    onError: () => toast.error("Failed to pause test"),
  });

  const startMutation = useMutation({
    mutationFn: (id: string) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return messageTestsApi.start(workspaceId, id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["message-tests", workspaceId] });
      toast.success("Test started");
    },
    onError: () => toast.error("Failed to start test"),
  });

  const completeMutation = useMutation({
    mutationFn: (id: string) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return messageTestsApi.complete(workspaceId, id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["message-tests", workspaceId] });
      toast.success("Test completed");
    },
    onError: () => toast.error("Failed to complete test"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return messageTestsApi.delete(workspaceId, id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["message-tests", workspaceId] });
      toast.success("Test deleted");
    },
    onError: () => toast.error("Failed to delete test"),
  });

  const filteredTests = tests.filter((test) => {
    const matchesSearch = test.name
      .toLowerCase()
      .includes(searchQuery.toLowerCase());
    const matchesStatus =
      statusFilter === "all" || test.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const getResponseRate = (test: MessageTest) => {
    if (test.messages_sent === 0) return 0;
    return Math.round((test.replies_received / test.messages_sent) * 100);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="size-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-2">
        <AlertCircle className="size-8 text-destructive" />
        <p className="text-muted-foreground">Failed to load experiments</p>
        <Button
          variant="outline"
          onClick={() =>
            queryClient.invalidateQueries({
              queryKey: ["message-tests", workspaceId],
            })
          }
        >
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Message Experiments
          </h1>
          <p className="text-muted-foreground">
            A/B test your outreach messages to find what works best
          </p>
        </div>
        <Button asChild>
          <Link href="/experiments/new">
            <FlaskConical className="mr-2 size-4" />
            New Experiment
          </Link>
        </Button>
      </div>

      {/* Stats Cards */}
      <motion.div
        className="grid gap-4 md:grid-cols-4"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {[
          { label: "Total Experiments", value: tests.length },
          {
            label: "Running",
            value: tests.filter((t) => t.status === "running").length,
          },
          {
            label: "Total Variants",
            value: tests.reduce((sum, t) => sum + t.total_variants, 0),
          },
          {
            label: "Avg Response Rate",
            value: `${
              tests.length > 0
                ? Math.round(
                    tests.reduce((sum, t) => sum + getResponseRate(t), 0) /
                      tests.length
                  )
                : 0
            }%`,
          },
        ].map((stat) => (
          <motion.div key={stat.label} variants={itemVariants}>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>{stat.label}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stat.value}</div>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </motion.div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search experiments..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10"
              />
            </div>
            <div className="flex gap-2">
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-[140px]">
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="draft">Draft</SelectItem>
                  <SelectItem value="running">Running</SelectItem>
                  <SelectItem value="paused">Paused</SelectItem>
                  <SelectItem value="completed">Completed</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Tests Table */}
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Experiment</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Variants</TableHead>
                <TableHead>Progress</TableHead>
                <TableHead>Response Rate</TableHead>
                <TableHead>Winner</TableHead>
                <TableHead className="w-[50px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <AnimatePresence mode="popLayout">
                {filteredTests.map((test) => {
                  const progress =
                    test.total_contacts > 0
                      ? (test.messages_sent / test.total_contacts) * 100
                      : 0;

                  return (
                    <motion.tr
                      key={test.id}
                      layout
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="group cursor-pointer hover:bg-muted/50"
                    >
                      <TableCell>
                        <Link
                          href={`/experiments/${test.id}`}
                          className="block"
                        >
                          <div className="font-medium">{test.name}</div>
                          <div className="text-sm text-muted-foreground line-clamp-1">
                            {test.description || "No description"}
                          </div>
                        </Link>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={statusColors[test.status]}
                        >
                          {test.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <FlaskConical className="size-4 text-muted-foreground" />
                          <span>{test.total_variants} variants</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          <Progress value={progress} className="h-2 w-24" />
                          <div className="text-xs text-muted-foreground">
                            {test.messages_sent.toLocaleString()} /{" "}
                            {test.total_contacts.toLocaleString()}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="font-medium">
                          {getResponseRate(test)}%
                        </div>
                      </TableCell>
                      <TableCell>
                        {test.winning_variant_id ? (
                          <Badge
                            variant="secondary"
                            className="bg-green-500/10 text-green-600"
                          >
                            <Trophy className="mr-1 size-3" />
                            Winner selected
                          </Badge>
                        ) : test.status === "completed" ? (
                          <span className="text-sm text-muted-foreground">
                            Pending
                          </span>
                        ) : (
                          <span className="text-sm text-muted-foreground">
                            -
                          </span>
                        )}
                      </TableCell>
                      <TableCell>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="opacity-0 group-hover:opacity-100"
                            >
                              <MoreHorizontal className="size-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            {test.status === "running" ? (
                              <DropdownMenuItem
                                onSelect={() => pauseMutation.mutate(test.id)}
                              >
                                <Pause className="mr-2 size-4" />
                                Pause
                              </DropdownMenuItem>
                            ) : test.status === "paused" ||
                              test.status === "draft" ? (
                              <DropdownMenuItem
                                onSelect={() => startMutation.mutate(test.id)}
                              >
                                <Play className="mr-2 size-4" />
                                {test.status === "draft" ? "Start" : "Resume"}
                              </DropdownMenuItem>
                            ) : null}
                            {(test.status === "running" ||
                              test.status === "paused") && (
                              <DropdownMenuItem
                                onSelect={() => completeMutation.mutate(test.id)}
                              >
                                <CheckCircle2 className="mr-2 size-4" />
                                Complete
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              variant="destructive"
                              onSelect={() => deleteMutation.mutate(test.id)}
                            >
                              <Trash2 className="mr-2 size-4" />
                              Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </motion.tr>
                  );
                })}
              </AnimatePresence>
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Empty state */}
      {filteredTests.length === 0 && !isLoading && (
        <div className="text-center py-12">
          <FlaskConical className="mx-auto size-12 text-muted-foreground mb-4" />
          <h3 className="text-lg font-medium mb-2">No experiments yet</h3>
          <p className="text-muted-foreground mb-4">
            Create your first A/B test to start optimizing your outreach
          </p>
          <Button asChild>
            <Link href="/experiments/new">Create Experiment</Link>
          </Button>
        </div>
      )}

      {/* Pagination */}
      {filteredTests.length > 0 && (
        <div className="flex items-center justify-between">
          <div className="text-sm text-muted-foreground">
            Showing {filteredTests.length} of {tests.length} experiments
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
      )}
    </div>
  );
}
