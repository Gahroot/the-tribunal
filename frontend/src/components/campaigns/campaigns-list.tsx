"use client";

import { useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { format } from "date-fns";
import {
  Plus,
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
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
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
import type { Campaign, CampaignStatus, CampaignType } from "@/types";

// Mock data for campaigns
const mockCampaigns: Campaign[] = [
  {
    id: "1",
    user_id: 1,
    name: "Spring Property Showcase",
    description: "Promote new spring listings to qualified leads",
    type: "sms",
    status: "running",
    sms_template: "Hi {{first_name}}, check out our new spring listings!",
    total_contacts: 1250,
    sent_count: 890,
    delivered_count: 856,
    failed_count: 34,
    responded_count: 145,
    messages_per_hour: 200,
    created_at: "2024-01-15T10:00:00Z",
    updated_at: "2024-01-20T14:30:00Z",
  },
  {
    id: "2",
    user_id: 1,
    name: "Open House Invitations",
    description: "Invite contacts to upcoming open houses",
    type: "email",
    status: "scheduled",
    email_subject: "You're Invited: Exclusive Open House This Weekend",
    email_template: "<p>Dear {{first_name}}, join us for an exclusive viewing...</p>",
    scheduled_start: "2024-01-25T09:00:00Z",
    total_contacts: 500,
    sent_count: 0,
    delivered_count: 0,
    failed_count: 0,
    responded_count: 0,
    messages_per_hour: 100,
    created_at: "2024-01-18T08:00:00Z",
    updated_at: "2024-01-18T08:00:00Z",
  },
  {
    id: "3",
    user_id: 1,
    name: "Follow-up Call Campaign",
    description: "AI voice calls to follow up with interested buyers",
    type: "voice",
    status: "paused",
    voice_script: "Hello {{first_name}}, I'm calling from...",
    agent_id: "agent-1",
    total_contacts: 200,
    sent_count: 87,
    delivered_count: 65,
    failed_count: 22,
    responded_count: 45,
    messages_per_hour: 30,
    created_at: "2024-01-10T12:00:00Z",
    updated_at: "2024-01-19T16:45:00Z",
  },
  {
    id: "4",
    user_id: 1,
    name: "Multi-Channel Nurture",
    description: "Comprehensive nurture campaign using SMS and Email",
    type: "multi_channel",
    status: "draft",
    sms_template: "Hi {{first_name}}! Quick update on properties in your area.",
    email_subject: "Weekly Market Update",
    email_template: "<p>Stay informed with our latest market insights...</p>",
    total_contacts: 0,
    sent_count: 0,
    delivered_count: 0,
    failed_count: 0,
    responded_count: 0,
    created_at: "2024-01-20T09:00:00Z",
    updated_at: "2024-01-20T09:00:00Z",
  },
  {
    id: "5",
    user_id: 1,
    name: "Re-engagement SMS Blast",
    description: "Re-engage cold leads with special offers",
    type: "sms",
    status: "completed",
    sms_template: "{{first_name}}, we miss you! Special offer inside...",
    total_contacts: 800,
    sent_count: 800,
    delivered_count: 756,
    failed_count: 44,
    responded_count: 89,
    created_at: "2024-01-05T10:00:00Z",
    updated_at: "2024-01-08T18:00:00Z",
    completed_at: "2024-01-08T18:00:00Z",
  },
];

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

  const filteredCampaigns = mockCampaigns.filter((campaign) => {
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
        <div className="flex items-center gap-2">
          <Button variant="outline" asChild>
            <Link href="/campaigns/sms/new">
              <MessageSquare className="mr-2 size-4" />
              New SMS Campaign
            </Link>
          </Button>
          <Button asChild>
            <Link href="/campaigns/new">
              <Plus className="mr-2 size-4" />
              Create Campaign
            </Link>
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <motion.div
        className="grid gap-4 md:grid-cols-4"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {[
          { label: "Total Campaigns", value: mockCampaigns.length },
          {
            label: "Active",
            value: mockCampaigns.filter((c) => c.status === "running").length,
          },
          {
            label: "Total Contacts",
            value: mockCampaigns.reduce((sum, c) => sum + c.total_contacts, 0),
          },
          {
            label: "Total Responses",
            value: mockCampaigns.reduce((sum, c) => sum + c.responded_count, 0),
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
                              <DropdownMenuItem>
                                <Pause className="mr-2 size-4" />
                                Pause
                              </DropdownMenuItem>
                            ) : campaign.status === "paused" ||
                              campaign.status === "draft" ? (
                              <DropdownMenuItem>
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
                            <DropdownMenuItem className="text-destructive">
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
          Showing {filteredCampaigns.length} of {mockCampaigns.length} campaigns
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
