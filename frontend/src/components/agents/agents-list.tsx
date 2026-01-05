"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Plus,
  Search,
  MoreHorizontal,
  Play,
  Pause,
  Settings2,
  Trash2,
  Bot,
  Phone,
  MessageSquare,
  Mic,
  Sparkles,
  Loader2,
  AlertCircle,
  Copy,
} from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/providers/auth-provider";
import { agentsApi } from "@/lib/api/agents";

const channelModeIcons: Record<string, React.ElementType> = {
  voice: Phone,
  text: MessageSquare,
  both: Sparkles,
};

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.1 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  visible: { opacity: 1, y: 0 },
};

export function AgentsList() {
  const [searchQuery, setSearchQuery] = useState("");
  const { workspaceId } = useAuth();
  const queryClient = useQueryClient();

  // Fetch agents from API
  const {
    data: agentsData,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["agents", workspaceId],
    queryFn: () => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return agentsApi.list(workspaceId, { active_only: false });
    },
    enabled: !!workspaceId,
  });

  // Toggle agent active status
  const toggleAgentMutation = useMutation({
    mutationFn: ({ agentId, isActive }: { agentId: string; isActive: boolean }) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return agentsApi.update(workspaceId, agentId, { is_active: isActive });
    },
    onSuccess: () => {
      if (workspaceId) {
        queryClient.invalidateQueries({ queryKey: ["agents", workspaceId] });
      }
      toast.success("Agent status updated");
    },
    onError: () => {
      toast.error("Failed to update agent status");
    },
  });

  // Delete agent
  const deleteAgentMutation = useMutation({
    mutationFn: (agentId: string) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return agentsApi.delete(workspaceId, agentId);
    },
    onSuccess: () => {
      if (workspaceId) {
        queryClient.invalidateQueries({ queryKey: ["agents", workspaceId] });
      }
      toast.success("Agent deleted");
    },
    onError: () => {
      toast.error("Failed to delete agent");
    },
  });

  // Duplicate agent
  const duplicateAgentMutation = useMutation({
    mutationFn: (agent: (typeof agents)[0]) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return agentsApi.create(workspaceId, {
        name: `${agent.name} (Copy)`,
        description: agent.description ?? undefined,
        channel_mode: agent.channel_mode,
        voice_provider: agent.voice_provider,
        voice_id: agent.voice_id,
        language: agent.language,
        system_prompt: agent.system_prompt,
        temperature: agent.temperature,
        text_response_delay_ms: agent.text_response_delay_ms,
        text_max_context_messages: agent.text_max_context_messages,
        calcom_event_type_id: agent.calcom_event_type_id ?? undefined,
        enabled_tools: agent.enabled_tools,
        tool_settings: agent.tool_settings,
      });
    },
    onSuccess: () => {
      if (workspaceId) {
        queryClient.invalidateQueries({ queryKey: ["agents", workspaceId] });
      }
      toast.success("Agent duplicated");
    },
    onError: () => {
      toast.error("Failed to duplicate agent");
    },
  });

  const agents = agentsData?.items ?? [];

  const filteredAgents = agents.filter(
    (agent) =>
      agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.description?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const activeAgents = agents.filter((a) => a.is_active).length;

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
        <p className="text-muted-foreground">Failed to load agents</p>
        <Button variant="outline" onClick={() => {
          if (workspaceId) {
            queryClient.invalidateQueries({ queryKey: ["agents", workspaceId] });
          }
        }}>
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
          <h1 className="text-2xl font-bold tracking-tight">AI Agents</h1>
          <p className="text-muted-foreground">
            Configure and manage your AI voice and text agents
          </p>
        </div>
        <Button asChild>
          <Link href="/agents/create">
            <Plus className="mr-2 size-4" />
            Create Agent
          </Link>
        </Button>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Total Agents</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{agents.length}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Active Agents</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{activeAgents}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Voice Enabled</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {
                agents.filter(
                  (a) => a.channel_mode === "voice" || a.channel_mode === "both"
                ).length
              }
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Search */}
      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search agents..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-10"
        />
      </div>

      {/* Agents Grid */}
      <motion.div
        className="grid gap-4 md:grid-cols-2 lg:grid-cols-3"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        <AnimatePresence mode="popLayout">
          {filteredAgents.map((agent) => {
            const ChannelIcon = channelModeIcons[agent.channel_mode] ?? Sparkles;

            return (
              <motion.div
                key={agent.id}
                layout
                variants={itemVariants}
                initial="hidden"
                animate="visible"
                exit={{ opacity: 0, scale: 0.9 }}
              >
                <Card className="group relative overflow-hidden">
                  <div
                    className={`absolute top-0 left-0 right-0 h-1 ${
                      agent.is_active ? "bg-green-500" : "bg-gray-400"
                    }`}
                  />
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between">
                      <div className="flex items-center gap-3">
                        <div className="flex size-10 items-center justify-center rounded-full bg-primary/10">
                          <Bot className="size-5 text-primary" />
                        </div>
                        <div>
                          <CardTitle className="text-lg">{agent.name}</CardTitle>
                          <div className="flex items-center gap-2 mt-1">
                            <Badge
                              variant="outline"
                              className="bg-blue-500/10 text-blue-500 border-blue-500/20"
                            >
                              {agent.voice_provider}
                            </Badge>
                          </div>
                        </div>
                      </div>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            className="opacity-0 group-hover:opacity-100"
                          >
                            <MoreHorizontal className="size-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem asChild>
                            <Link href={`/agents/${agent.id}`}>
                              <Settings2 className="mr-2 size-4" />
                              Configure
                            </Link>
                          </DropdownMenuItem>
                          {agent.is_active ? (
                            <DropdownMenuItem
                              onClick={() => toggleAgentMutation.mutate({ agentId: agent.id, isActive: false })}
                            >
                              <Pause className="mr-2 size-4" />
                              Deactivate
                            </DropdownMenuItem>
                          ) : (
                            <DropdownMenuItem
                              onClick={() => toggleAgentMutation.mutate({ agentId: agent.id, isActive: true })}
                            >
                              <Play className="mr-2 size-4" />
                              Activate
                            </DropdownMenuItem>
                          )}
                          <DropdownMenuItem
                            onClick={() => duplicateAgentMutation.mutate(agent)}
                            disabled={duplicateAgentMutation.isPending}
                          >
                            <Copy className="mr-2 size-4" />
                            Duplicate
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={() => deleteAgentMutation.mutate(agent.id)}
                          >
                            <Trash2 className="mr-2 size-4" />
                            Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <p className="text-sm text-muted-foreground line-clamp-2">
                      {agent.description ?? "No description"}
                    </p>
                    <div className="flex items-center gap-4 text-sm">
                      <div className="flex items-center gap-1.5">
                        <ChannelIcon className="size-4 text-muted-foreground" />
                        <span className="capitalize">
                          {agent.channel_mode === "both"
                            ? "Voice & Text"
                            : agent.channel_mode}
                        </span>
                      </div>
                      {agent.voice_id && (
                        <div className="flex items-center gap-1.5">
                          <Mic className="size-4 text-muted-foreground" />
                          <span className="capitalize">{agent.voice_id}</span>
                        </div>
                      )}
                    </div>
                  </CardContent>
                  <CardFooter className="border-t pt-4">
                    <div className="flex items-center justify-between w-full">
                      <div className="flex items-center gap-2">
                        <div
                          className={`size-2 rounded-full ${
                            agent.is_active ? "bg-green-500" : "bg-gray-400"
                          }`}
                        />
                        <span className="text-sm text-muted-foreground">
                          {agent.is_active ? "Active" : "Inactive"}
                        </span>
                      </div>
                      <Button variant="outline" size="sm" asChild>
                        <Link href={`/agents/${agent.id}`}>Configure</Link>
                      </Button>
                    </div>
                  </CardFooter>
                </Card>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </motion.div>
    </div>
  );
}
