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
  Copy,
  Trash2,
  Mail,
  MessageSquare,
  Phone,
  Layers,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
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
import { useAuth } from "@/providers/auth-provider";
import type { Campaign, CampaignStatus, CampaignType } from "@/types";
import { campaignsApi } from "@/lib/api/campaigns";

const statusColors: Record<CampaignStatus, string> = {
  draft: "bg-gray-500/10 text-gray-500 border-gray-500/20",
  scheduled: "bg-blue-500/10 text-blue-500 border-blue-500/20",
  running: "bg-green-500/10 text-green-500 border-green-500/20",
  paused: "bg-yellow-500/10 text-yellow-500 border-yellow-500/20",
  completed: "bg-purple-500/10 text-purple-500 border-purple-500/20",
  cancelled: "bg-red-500/10 text-red-500 border-red-500/20",
};

const typeIcons: Record<CampaignType, React.ElementType> = {
  sms: MessageSquare,
  email: Mail,
  voice: Phone,
  multi_channel: Layers,
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

export function CampaignsList() {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const { workspaceId } = useAuth();

  const queryClient = useQueryClient();

  const { data: campaignsData, isLoading, error } = useQuery({
    queryKey: ["campaigns", workspaceId],
    queryFn: () => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return campaignsApi.list(workspaceId);
    },
    enabled: !!workspaceId,
  });

  const campaigns = campaignsData?.campaigns ?? [];

  const pauseMutation = useMutation({
    mutationFn: (id: string) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return campaignsApi.pause(workspaceId, id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      toast.success("Campaign paused");
    },
    onError: () => toast.error("Failed to pause campaign"),
  });

  const startMutation = useMutation({
    mutationFn: (id: string) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return campaignsApi.start(workspaceId, id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      toast.success("Campaign started");
    },
    onError: () => toast.error("Failed to start campaign"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return campaignsApi.delete(workspaceId, id);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      toast.success("Campaign deleted");
    },
    onError: () => toast.error("Failed to delete campaign"),
  });

  const filteredCampaigns = campaigns.filter((campaign) => {
    const matchesSearch = campaign.name
      .toLowerCase()
      .includes(searchQuery.toLowerCase());
    const matchesStatus =
      statusFilter === "all" || campaign.status === statusFilter;
    const matchesType = typeFilter === "all" || campaign.type === typeFilter;
    return matchesSearch && matchesStatus && matchesType;
  });

  const getDeliveryRate = (campaign: Campaign) => {
    if (campaign.sent_count === 0) return 0;
    return Math.round((campaign.delivered_count / campaign.sent_count) * 100);
  };

  const getResponseRate = (campaign: Campaign) => {
    if (campaign.delivered_count === 0) return 0;
    return Math.round(
      (campaign.responded_count / campaign.delivered_count) * 100
    );
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
        <p className="text-muted-foreground">Failed to load campaigns</p>
        <Button variant="outline" onClick={() => queryClient.invalidateQueries({ queryKey: ["campaigns"] })}>
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
          <h1 className="text-2xl font-bold tracking-tight">Campaigns</h1>
          <p className="text-muted-foreground">
            Create and manage your outreach campaigns
          </p>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button>
              New Campaign
              <ChevronDown className="ml-2 size-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-64">
            <DropdownMenuItem asChild>
              <Link href="/campaigns/sms/new" className="flex items-center cursor-pointer">
                <MessageSquare className="mr-2 size-4" />
                SMS Campaign
              </Link>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <Link href="/campaigns/voice/new" className="flex items-center cursor-pointer">
                <Phone className="mr-2 size-4" />
                <div>
                  <div>Voice Campaign with SMS Fallback</div>
                  <div className="text-xs text-muted-foreground">AI calls with auto-text on failures</div>
                </div>
              </Link>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem disabled className="flex items-center justify-between opacity-60">
              <span className="flex items-center">
                <Mail className="mr-2 size-4" />
                Email Campaign
              </span>
              <span className="text-xs bg-muted px-1.5 py-0.5 rounded">Coming Soon</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Stats Cards */}
      <motion.div
        className="grid gap-4 md:grid-cols-4"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {[
          { label: "Total Campaigns", value: campaigns.length },
          {
            label: "Active",
            value: campaigns.filter((c) => c.status === "running").length,
          },
          {
            label: "Total Contacts",
            value: campaigns.reduce((sum, c) => sum + c.total_contacts, 0),
          },
          {
            label: "Total Responses",
            value: campaigns.reduce((sum, c) => sum + c.responded_count, 0),
          },
        ].map((stat) => (
          <motion.div key={stat.label} variants={itemVariants}>
            <Card>
              <CardHeader className="pb-2">
                <CardDescription>{stat.label}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {stat.value.toLocaleString()}
                </div>
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
                placeholder="Search campaigns..."
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
                  <SelectItem value="scheduled">Scheduled</SelectItem>
                  <SelectItem value="running">Running</SelectItem>
                  <SelectItem value="paused">Paused</SelectItem>
                  <SelectItem value="completed">Completed</SelectItem>
                </SelectContent>
              </Select>
              <Select value={typeFilter} onValueChange={setTypeFilter}>
                <SelectTrigger className="w-[140px]">
                  <SelectValue placeholder="Type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Types</SelectItem>
                  <SelectItem value="sms">SMS</SelectItem>
                  <SelectItem value="email">Email</SelectItem>
                  <SelectItem value="voice">Voice</SelectItem>
                  <SelectItem value="multi_channel">Multi-Channel</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Campaigns Table */}
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Campaign</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Progress</TableHead>
                <TableHead>Delivery</TableHead>
                <TableHead>Response</TableHead>
                <TableHead className="w-[50px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <AnimatePresence mode="popLayout">
                {filteredCampaigns.map((campaign) => {
                  const TypeIcon = typeIcons[campaign.type];
                  const progress =
                    campaign.total_contacts > 0
                      ? (campaign.sent_count / campaign.total_contacts) * 100
                      : 0;

                  return (
                    <motion.tr
                      key={campaign.id}
                      layout
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="group cursor-pointer hover:bg-muted/50"
                    >
                      <TableCell>
                        <Link
                          href={`/campaigns/${campaign.id}`}
                          className="block"
                        >
                          <div className="font-medium">{campaign.name}</div>
                          <div className="text-sm text-muted-foreground line-clamp-1">
                            {campaign.description}
                          </div>
                        </Link>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <TypeIcon className="size-4 text-muted-foreground" />
                          <span className="capitalize">
                            {campaign.type.replace("_", " ")}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={statusColors[campaign.status]}
                        >
                          {campaign.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          <Progress value={progress} className="h-2 w-24" />
                          <div className="text-xs text-muted-foreground">
                            {campaign.sent_count.toLocaleString()} /{" "}
                            {campaign.total_contacts.toLocaleString()}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="font-medium">
                          {getDeliveryRate(campaign)}%
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="font-medium">
                          {getResponseRate(campaign)}%
                        </div>
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
                            {campaign.status === "running" ? (
                              <DropdownMenuItem onClick={() => pauseMutation.mutate(campaign.id)}>
                                <Pause className="mr-2 size-4" />
                                Pause
                              </DropdownMenuItem>
                            ) : campaign.status === "paused" ||
                              campaign.status === "draft" ? (
                              <DropdownMenuItem onClick={() => startMutation.mutate(campaign.id)}>
                                <Play className="mr-2 size-4" />
                                {campaign.status === "draft"
                                  ? "Start"
                                  : "Resume"}
                              </DropdownMenuItem>
                            ) : null}
                            <DropdownMenuItem>
                              <Copy className="mr-2 size-4" />
                              Duplicate
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem className="text-destructive" onClick={() => deleteMutation.mutate(campaign.id)}>
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

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-muted-foreground">
          Showing {filteredCampaigns.length} of {campaigns.length} campaigns
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
