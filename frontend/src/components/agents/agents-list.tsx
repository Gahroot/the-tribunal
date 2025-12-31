"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
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
  Volume2,
  Sparkles,
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { Agent } from "@/types";

// Mock data
const mockAgents: Agent[] = [
  {
    id: "agent-1",
    user_id: 1,
    name: "Sarah",
    description: "Friendly sales agent specializing in property inquiries and scheduling viewings",
    pricing_tier: "premium",
    system_prompt: "You are Sarah, a friendly and professional real estate sales agent...",
    voice: "alloy",
    is_active: true,
    channel_mode: "both",
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-20T00:00:00Z",
  },
  {
    id: "agent-2",
    user_id: 1,
    name: "Mike",
    description: "Technical support agent for handling service inquiries and troubleshooting",
    pricing_tier: "balanced",
    system_prompt: "You are Mike, a patient and knowledgeable support agent...",
    voice: "echo",
    is_active: true,
    channel_mode: "voice",
    created_at: "2024-01-05T00:00:00Z",
    updated_at: "2024-01-18T00:00:00Z",
  },
  {
    id: "agent-3",
    user_id: 1,
    name: "Emma",
    description: "Appointment scheduler focused on booking and managing meetings",
    pricing_tier: "budget",
    system_prompt: "You are Emma, an efficient appointment scheduling assistant...",
    voice: "shimmer",
    is_active: false,
    channel_mode: "text",
    created_at: "2024-01-10T00:00:00Z",
    updated_at: "2024-01-15T00:00:00Z",
  },
  {
    id: "agent-4",
    user_id: 1,
    name: "Alex",
    description: "Lead qualification agent for initial contact and screening",
    pricing_tier: "premium-mini",
    system_prompt: "You are Alex, a skilled lead qualification specialist...",
    voice: "onyx",
    is_active: true,
    channel_mode: "both",
    created_at: "2024-01-12T00:00:00Z",
    updated_at: "2024-01-20T00:00:00Z",
  },
];

const pricingTierColors: Record<string, string> = {
  budget: "bg-gray-500/10 text-gray-500 border-gray-500/20",
  balanced: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  "premium-mini": "bg-purple-500/10 text-purple-500 border-purple-500/20",
  premium: "bg-amber-500/10 text-amber-500 border-amber-500/20",
};

const channelModeIcons: Record<string, React.ElementType> = {
  voice: Phone,
  text: MessageSquare,
  both: Sparkles,
};

const voiceOptions = [
  { value: "alloy", label: "Alloy", description: "Neutral and balanced" },
  { value: "echo", label: "Echo", description: "Warm and friendly" },
  { value: "fable", label: "Fable", description: "Expressive and dynamic" },
  { value: "onyx", label: "Onyx", description: "Deep and authoritative" },
  { value: "nova", label: "Nova", description: "Young and energetic" },
  { value: "shimmer", label: "Shimmer", description: "Soft and gentle" },
];

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
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);

  const filteredAgents = mockAgents.filter(
    (agent) =>
      agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      agent.description?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const activeAgents = mockAgents.filter((a) => a.is_active).length;

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
        <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 size-4" />
              Create Agent
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Create New Agent</DialogTitle>
              <DialogDescription>
                Configure a new AI agent for voice or text interactions
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="agent-name">Agent Name</Label>
                  <Input id="agent-name" placeholder="e.g., Sarah" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="pricing-tier">Pricing Tier</Label>
                  <Select defaultValue="balanced">
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="budget">Budget</SelectItem>
                      <SelectItem value="balanced">Balanced</SelectItem>
                      <SelectItem value="premium-mini">Premium Mini</SelectItem>
                      <SelectItem value="premium">Premium</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="description">Description</Label>
                <Input
                  id="description"
                  placeholder="Brief description of the agent's role"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="voice">Voice</Label>
                  <Select defaultValue="alloy">
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {voiceOptions.map((voice) => (
                        <SelectItem key={voice.value} value={voice.value}>
                          <div className="flex items-center gap-2">
                            <Volume2 className="size-4" />
                            <span>{voice.label}</span>
                            <span className="text-xs text-muted-foreground">
                              - {voice.description}
                            </span>
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="channel-mode">Channel Mode</Label>
                  <Select defaultValue="both">
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="voice">Voice Only</SelectItem>
                      <SelectItem value="text">Text Only</SelectItem>
                      <SelectItem value="both">Voice & Text</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="system-prompt">System Prompt</Label>
                <Textarea
                  id="system-prompt"
                  placeholder="You are a helpful assistant..."
                  rows={6}
                />
                <p className="text-xs text-muted-foreground">
                  Define the agent's personality, knowledge, and behavior
                </p>
              </div>
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setIsCreateDialogOpen(false)}
              >
                Cancel
              </Button>
              <Button onClick={() => setIsCreateDialogOpen(false)}>
                Create Agent
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Total Agents</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{mockAgents.length}</div>
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
                mockAgents.filter(
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
            const ChannelIcon = channelModeIcons[agent.channel_mode];
            const voiceInfo = voiceOptions.find((v) => v.value === agent.voice);

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
                              className={pricingTierColors[agent.pricing_tier]}
                            >
                              {agent.pricing_tier.replace("-", " ")}
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
                          <DropdownMenuItem>
                            <Settings2 className="mr-2 size-4" />
                            Configure
                          </DropdownMenuItem>
                          {agent.is_active ? (
                            <DropdownMenuItem>
                              <Pause className="mr-2 size-4" />
                              Deactivate
                            </DropdownMenuItem>
                          ) : (
                            <DropdownMenuItem>
                              <Play className="mr-2 size-4" />
                              Activate
                            </DropdownMenuItem>
                          )}
                          <DropdownMenuSeparator />
                          <DropdownMenuItem className="text-destructive">
                            <Trash2 className="mr-2 size-4" />
                            Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <p className="text-sm text-muted-foreground line-clamp-2">
                      {agent.description}
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
                      {agent.voice && (
                        <div className="flex items-center gap-1.5">
                          <Mic className="size-4 text-muted-foreground" />
                          <span className="capitalize">{agent.voice}</span>
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
