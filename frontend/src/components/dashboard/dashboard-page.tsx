"use client";

import type React from "react";
import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Users,
  Phone,
  MessageSquare,
  Megaphone,
  TrendingUp,
  TrendingDown,
  ArrowUpRight,
  Clock,
  CheckCircle,
  XCircle,
  Calendar,
  CalendarDays,
  CalendarCheck,
  UserX,
  Bot,
  Loader2,
  AlertCircle,
  Bell,
} from "lucide-react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { nudgesApi } from "@/lib/api/nudges";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { AppointmentPerformanceCard } from "@/components/dashboard/appointment-performance-card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboard } from "@/hooks/useDashboard";
import { useWorkspaceId } from "@/hooks/use-workspace-id";
import type {
  DashboardStats,
  RecentActivity,
  CampaignStat,
  AgentStat,
  TodayOverview,
  AppointmentStats,
} from "@/lib/api/dashboard";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.07 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { type: "spring" as const, stiffness: 300, damping: 24 },
  },
};

function formatNumber(num: number): string {
  if (num >= 1000000) {
    return `${(num / 1000000).toFixed(1)}M`;
  }
  if (num >= 1000) {
    return `${(num / 1000).toFixed(1)}K`;
  }
  return num.toLocaleString();
}

function isTrendUp(change: string): boolean {
  return change.startsWith("+") && change !== "+0" && change !== "+0%";
}

function AnimatedNumber({ value }: { value: number }) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    const end = value;
    if (end === 0) return;
    const duration = 1000;
    const startTime = performance.now();

    const step = (currentTime: number) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(Math.floor(eased * end));
      if (progress < 1) requestAnimationFrame(step);
    };

    requestAnimationFrame(step);
  }, [value]);

  return <span>{formatNumber(display)}</span>;
}

interface StatCardProps {
  title: string;
  value: number;
  change: string;
  href: string;
  icon: React.ReactNode;
}

function StatCard({ title, value, change, href, icon }: StatCardProps) {
  const trendUp = isTrendUp(change);

  return (
    <Link href={href}>
      <Card className="card-glow card-interactive hover:bg-muted/50 transition-colors cursor-pointer">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardDescription>{title}</CardDescription>
          <div className="rounded-lg bg-primary/10 p-2 ring-1 ring-primary/20">
            {icon}
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div className="text-2xl font-bold tabular-nums"><AnimatedNumber value={value} /></div>
            <div
              className={`flex items-center text-sm ${
                trendUp ? "text-success" : "text-destructive"
              }`}
            >
              {trendUp ? (
                <TrendingUp className="mr-1 size-4" />
              ) : (
                <TrendingDown className="mr-1 size-4" />
              )}
              {change}
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function StatCardSkeleton() {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="size-4 rounded" />
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between">
          <Skeleton className="h-8 w-16" />
          <Skeleton className="h-4 w-12" />
        </div>
      </CardContent>
    </Card>
  );
}

interface StatsGridProps {
  stats: DashboardStats | undefined;
  isLoading: boolean;
}

function StatsGrid({ stats, isLoading }: StatsGridProps) {
  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[1, 2, 3, 4].map((i) => (
          <StatCardSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (!stats) return null;

  return (
    <motion.div
      className="grid gap-4 md:grid-cols-2 lg:grid-cols-4"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      <motion.div variants={itemVariants}>
        <StatCard
          title="Total Contacts"
          value={stats.total_contacts}
          change={stats.contacts_change}
          href="/contacts"
          icon={<Users className="size-4 text-primary" />}
        />
      </motion.div>
      <motion.div variants={itemVariants}>
        <StatCard
          title="Active Campaigns"
          value={stats.active_campaigns}
          change={stats.campaigns_change}
          href="/campaigns"
          icon={<Megaphone className="size-4 text-primary" />}
        />
      </motion.div>
      <motion.div variants={itemVariants}>
        <StatCard
          title="Calls Today"
          value={stats.calls_today}
          change={stats.calls_change}
          href="/calls"
          icon={<Phone className="size-4 text-primary" />}
        />
      </motion.div>
      <motion.div variants={itemVariants}>
        <StatCard
          title="Messages Sent"
          value={stats.messages_sent}
          change={stats.messages_change}
          href="/campaigns"
          icon={<MessageSquare className="size-4 text-primary" />}
        />
      </motion.div>
    </motion.div>
  );
}

interface ActiveCampaignsCardProps {
  campaigns: CampaignStat[];
  isLoading: boolean;
}

function ActiveCampaignsCard({ campaigns, isLoading }: ActiveCampaignsCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="gradient-heading">Active Campaigns</CardTitle>
          <CardDescription>
            Currently running and scheduled campaigns
          </CardDescription>
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link href="/campaigns">
            View All
            <ArrowUpRight className="ml-2 size-4" />
          </Link>
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <>
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex items-center gap-4 p-3 rounded-lg border">
                <div className="flex-1 space-y-2">
                  <div className="flex items-center justify-between">
                    <Skeleton className="h-5 w-40" />
                    <Skeleton className="h-4 w-16" />
                  </div>
                  <Skeleton className="h-2 w-full" />
                </div>
              </div>
            ))}
          </>
        ) : campaigns.length === 0 ? (
          <div className="text-center py-6 text-muted-foreground">
            No active campaigns. Create one to get started!
          </div>
        ) : (
          campaigns.map((campaign) => (
            <div
              key={campaign.id}
              className="flex items-center gap-4 p-3 rounded-lg border"
            >
              <div className="flex-1 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{campaign.name}</span>
                    <Badge
                      variant="outline"
                      className={
                        campaign.status === "running"
                          ? "bg-success/10 text-success border-success/20"
                          : "bg-info/10 text-info border-info/20"
                      }
                    >
                      {campaign.status}
                    </Badge>
                  </div>
                  <span className="text-sm text-muted-foreground">
                    {campaign.sent}/{campaign.total}
                  </span>
                </div>
                <Progress value={campaign.progress} className="h-2" />
              </div>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

interface AgentsCardProps {
  agents: AgentStat[];
  isLoading: boolean;
}

function AgentsCard({ agents, isLoading }: AgentsCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 gradient-heading">
          <Bot className="size-5" />
          AI Agents
        </CardTitle>
        <CardDescription>Performance this week</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <>
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Skeleton className="size-8 rounded-full" />
                  <div>
                    <Skeleton className="h-4 w-20 mb-1" />
                    <Skeleton className="h-3 w-16" />
                  </div>
                </div>
                <div className="text-right">
                  <Skeleton className="h-4 w-12 mb-1" />
                  <Skeleton className="h-3 w-8" />
                </div>
              </div>
            ))}
          </>
        ) : agents.length === 0 ? (
          <div className="text-center py-6 text-muted-foreground">
            No agents configured yet.
          </div>
        ) : (
          agents.map((agent, index) => (
            <div key={agent.id} className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="flex size-8 items-center justify-center rounded-full bg-primary/10 text-sm font-medium">
                  {index + 1}
                </div>
                <div>
                  <p className="font-medium">{agent.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {agent.calls} calls, {agent.messages} messages
                  </p>
                </div>
              </div>
              <div className="text-right">
                <p className="font-medium text-success">
                  {agent.success_rate}%
                </p>
                <p className="text-xs text-muted-foreground">success</p>
              </div>
            </div>
          ))
        )}
        <Button variant="outline" className="w-full" asChild>
          <Link href="/agents">Manage Agents</Link>
        </Button>
      </CardContent>
    </Card>
  );
}

interface RecentActivityCardProps {
  activities: RecentActivity[];
  isLoading: boolean;
}

function RecentActivityCard({ activities, isLoading }: RecentActivityCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="gradient-heading">Recent Activity</CardTitle>
        <CardDescription>Latest interactions and updates</CardDescription>
      </CardHeader>
      <CardContent>
        <ScrollArea className="max-h-[400px]">
          <div className="space-y-4 pr-3">
            {isLoading ? (
              <>
                {[1, 2, 3, 4, 5].map((i) => (
                  <div key={i} className="flex items-center gap-4 text-sm">
                    <Skeleton className="size-9 rounded-full" />
                    <div className="flex-1">
                      <Skeleton className="h-4 w-48 mb-1" />
                      <Skeleton className="h-3 w-24" />
                    </div>
                    <Skeleton className="size-4" />
                  </div>
                ))}
              </>
            ) : activities.length === 0 ? (
              <div className="text-center py-6 text-muted-foreground">
                No recent activity yet.
              </div>
            ) : (
              activities.map((activity) => (
                <div key={activity.id} className="flex items-center gap-4 text-sm">
                  <Avatar className="size-9">
                    <AvatarFallback className="text-xs">
                      {activity.initials}
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex-1">
                    <p>
                      <span className="font-medium">{activity.contact}</span>{" "}
                      <span className="text-muted-foreground">{activity.action}</span>
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {activity.time}
                      {activity.duration && ` - ${activity.duration}`}
                    </p>
                  </div>
                  {activity.type === "call" && (
                    <Phone className="size-4 text-muted-foreground" />
                  )}
                  {activity.type === "sms" && (
                    <MessageSquare className="size-4 text-muted-foreground" />
                  )}
                  {activity.type === "campaign" && (
                    <Megaphone className="size-4 text-muted-foreground" />
                  )}
                  {activity.type === "booking" && (
                    <Calendar className="size-4 text-muted-foreground" />
                  )}
                </div>
              ))
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}

interface TodayOverviewCardProps {
  overview: TodayOverview | undefined;
  isLoading: boolean;
}

function TodayOverviewCard({ overview, isLoading }: TodayOverviewCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="gradient-heading">Today&apos;s Overview</CardTitle>
        <CardDescription className="flex items-center gap-1.5">
          <Phone className="size-3" />
          <MessageSquare className="size-3" />
          Outbound call &amp; SMS delivery status
        </CardDescription>
      </CardHeader>
      <CardContent>
        <TooltipProvider>
          <div className="grid grid-cols-3 gap-4 text-center">
            {isLoading ? (
              <>
                {[1, 2, 3].map((i) => (
                  <div key={i} className="space-y-1">
                    <Skeleton className="h-8 w-12 mx-auto" />
                    <Skeleton className="h-3 w-16 mx-auto" />
                  </div>
                ))}
              </>
            ) : (
              <>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <div className="space-y-1 cursor-default">
                      <div className="flex items-center justify-center gap-1 text-success">
                        <CheckCircle className="size-4" />
                        <span className="text-2xl font-bold">
                          {overview?.completed ?? 0}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground">Completed</p>
                    </div>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>Calls answered &amp; SMS delivered or sent today</p>
                  </TooltipContent>
                </Tooltip>

                <Tooltip>
                  <TooltipTrigger asChild>
                    <div className="space-y-1 cursor-default">
                      <div className="flex items-center justify-center gap-1 text-warning">
                        <Clock className="size-4" />
                        <span className="text-2xl font-bold">
                          {overview?.pending ?? 0}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground">Pending</p>
                    </div>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>Calls &amp; messages currently queued or in progress</p>
                  </TooltipContent>
                </Tooltip>

                <Tooltip>
                  <TooltipTrigger asChild>
                    <div className="space-y-1 cursor-default">
                      <div className="flex items-center justify-center gap-1 text-destructive">
                        <XCircle className="size-4" />
                        <span className="text-2xl font-bold">
                          {overview?.failed ?? 0}
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground">Failed</p>
                    </div>
                  </TooltipTrigger>
                  <TooltipContent>
                    <p>Calls &amp; messages that could not be delivered today</p>
                  </TooltipContent>
                </Tooltip>
              </>
            )}
          </div>
        </TooltipProvider>
      </CardContent>
    </Card>
  );
}

function QuickActionsCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="gradient-heading">Quick Actions</CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-2">
        <Button variant="outline" className="justify-start" asChild>
          <Link href="/campaigns/new">
            <Megaphone className="mr-2 size-4" />
            New Campaign
          </Link>
        </Button>
        <Button variant="outline" className="justify-start" asChild>
          <Link href="/?import=true">
            <Users className="mr-2 size-4" />
            Import Contacts
          </Link>
        </Button>
        <Button variant="outline" className="justify-start" asChild>
          <Link href="/agents">
            <Bot className="mr-2 size-4" />
            Configure Agent
          </Link>
        </Button>
        <Button variant="outline" className="justify-start" asChild>
          <Link href="/calls">
            <Phone className="mr-2 size-4" />
            View Call Logs
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}

interface AppointmentStatsCardProps {
  appointmentStats: AppointmentStats | undefined;
  isLoading: boolean;
}

function AppointmentStatsCard({ appointmentStats, isLoading }: AppointmentStatsCardProps) {
  const showUpRate = appointmentStats?.show_up_rate_30d ?? null;

  const rateColor =
    showUpRate === null
      ? "text-muted-foreground"
      : showUpRate >= 70
        ? "text-success"
        : showUpRate >= 50
          ? "text-warning"
          : "text-destructive";

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2 gradient-heading">
            <CalendarDays className="size-5" />
            Appointments
          </CardTitle>
          <CardDescription>Scheduling performance</CardDescription>
        </div>
        <Button variant="outline" size="sm" asChild>
          <Link href="/calendar">
            View Calendar
            <ArrowUpRight className="ml-2 size-4" />
          </Link>
        </Button>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {isLoading ? (
            <>
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="space-y-1 text-center">
                  <Skeleton className="h-8 w-12 mx-auto" />
                  <Skeleton className="h-3 w-16 mx-auto" />
                  <Skeleton className="h-3 w-20 mx-auto" />
                </div>
              ))}
            </>
          ) : (
            <>
              <div className="space-y-1 text-center">
                <div className="flex items-center justify-center gap-1 text-info">
                  <Calendar className="size-4" />
                  <span className="text-2xl font-bold">
                    {appointmentStats?.appointments_today ?? 0}
                  </span>
                </div>
                <p className="text-xs font-medium">Today</p>
                <p className="text-xs text-muted-foreground">Scheduled</p>
              </div>

              <div className="space-y-1 text-center">
                <div className="flex items-center justify-center gap-1 text-primary">
                  <CalendarCheck className="size-4" />
                  <span className="text-2xl font-bold">
                    {appointmentStats?.appointments_this_week ?? 0}
                  </span>
                </div>
                <p className="text-xs font-medium">This Week</p>
                <p className="text-xs text-muted-foreground">Upcoming</p>
              </div>

              <div className="space-y-1 text-center">
                <div className={`flex items-center justify-center gap-1 ${rateColor}`}>
                  <TrendingUp className="size-4" />
                  <span className="text-2xl font-bold">
                    {showUpRate !== null ? `${showUpRate}%` : "—"}
                  </span>
                </div>
                <p className="text-xs font-medium">Show-Up Rate</p>
                <p className="text-xs text-muted-foreground">
                  {showUpRate !== null ? "Last 30 days" : "Not enough data"}
                </p>
              </div>

              <div className="space-y-1 text-center">
                <div className="flex items-center justify-center gap-1 text-destructive">
                  <UserX className="size-4" />
                  <span className="text-2xl font-bold">
                    {appointmentStats?.no_shows_30d ?? 0}
                  </span>
                </div>
                <p className="text-xs font-medium">No-Shows</p>
                <p className="text-xs text-muted-foreground">Last 30 days</p>
              </div>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function ErrorState({ error }: { error: Error }) {
  return (
    <div className="p-6">
      <Card className="border-destructive">
        <CardContent className="flex items-center gap-4 py-6">
          <AlertCircle className="size-8 text-destructive" />
          <div>
            <h3 className="font-semibold">Failed to load dashboard</h3>
            <p className="text-sm text-muted-foreground">
              {error.message || "An unexpected error occurred"}
            </p>
          </div>
          <Button
            variant="outline"
            className="ml-auto"
            onClick={() => window.location.reload()}
          >
            Retry
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function NudgesCard({ workspaceId }: { workspaceId: string | null }) {
  const { data: nudgeStats, isLoading } = useQuery({
    queryKey: ["nudgeStats", workspaceId],
    queryFn: () => nudgesApi.getStats(workspaceId!),
    enabled: !!workspaceId,
    refetchInterval: 60000,
  });

  const pending = nudgeStats?.pending ?? 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 gradient-heading">
          <Bell className="size-5" />
          Nudges
        </CardTitle>
        <CardDescription>Relationship reminders</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-8 w-32" />
        ) : pending > 0 ? (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="text-2xl font-bold text-orange-500">{pending}</span>
              <span className="text-sm text-muted-foreground">
                nudge{pending !== 1 ? "s" : ""} pending
              </span>
            </div>
            <Button variant="outline" size="sm" asChild>
              <Link href="/nudges">
                View Nudges
                <ArrowUpRight className="ml-2 size-4" />
              </Link>
            </Button>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No pending nudges 🎉</p>
        )}
      </CardContent>
    </Card>
  );
}

export function DashboardPage() {
  const workspaceId = useWorkspaceId();
  const { data, isLoading, error, isFetching } = useDashboard(workspaceId ?? "");

  if (error && !data) {
    return <ErrorState error={error as Error} />;
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight gradient-heading">
            Dashboard
            {isFetching && !isLoading && (
              <Loader2 className="ml-2 inline size-4 animate-spin text-muted-foreground" />
            )}
          </h1>
          <p className="text-muted-foreground">
            Welcome back! Here&apos;s an overview of your CRM activity.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" asChild>
            <Link href="/campaigns/new">New Campaign</Link>
          </Button>
          <Button asChild>
            <Link href="/contacts">
              <Users className="mr-2 size-4" />
              View Contacts
            </Link>
          </Button>
        </div>
      </div>

      {/* Stats Grid */}
      <StatsGrid stats={data?.stats} isLoading={isLoading} />

      {/* Appointment KPIs */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
      >
        <AppointmentStatsCard
          appointmentStats={data?.appointment_stats}
          isLoading={isLoading}
        />
      </motion.div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Active Campaigns */}
        <motion.div
          className="lg:col-span-2"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <ActiveCampaignsCard
            campaigns={data?.campaign_stats ?? []}
            isLoading={isLoading}
          />
        </motion.div>

        {/* AI Agents Performance */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <AgentsCard agents={data?.agent_stats ?? []} isLoading={isLoading} />
        </motion.div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Recent Activity */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
        >
          <RecentActivityCard
            activities={data?.recent_activity ?? []}
            isLoading={isLoading}
          />
        </motion.div>

        {/* Quick Actions & Metrics */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className="space-y-6"
        >
          {/* Today's Overview */}
          <TodayOverviewCard
            overview={data?.today_overview}
            isLoading={isLoading}
          />

          {/* Nudges summary */}
          <NudgesCard workspaceId={workspaceId} />

          {/* Quick Actions */}
          <QuickActionsCard />
        </motion.div>
      </div>

      {/* Show-up Rate Analytics */}
      {workspaceId && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6 }}
        >
          <AppointmentPerformanceCard workspaceId={workspaceId} />
        </motion.div>
      )}
    </div>
  );
}
