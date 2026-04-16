"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { AlertCircle, Loader2, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { AppointmentPerformanceCard } from "@/components/dashboard/appointment-performance-card";
import { DashboardStatsGrid } from "@/components/dashboard/dashboard-stats";
import {
  ActiveCampaignsCard,
  AgentsCard,
  AppointmentStatsCard,
} from "@/components/dashboard/performance-metrics";
import { RecentActivityFeed } from "@/components/dashboard/recent-activity-feed";
import {
  NudgesCard,
  QuickActionsCard,
  TodayOverviewCard,
} from "@/components/dashboard/today-overview";
import { useDashboard } from "@/hooks/useDashboard";
import { useWorkspaceId } from "@/hooks/use-workspace-id";

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

export function DashboardPage() {
  const workspaceId = useWorkspaceId();
  const { data, isPending, error, isFetching } = useDashboard(workspaceId ?? "");

  if (error && !data) {
    return <ErrorState error={error as Error} />;
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight gradient-heading">
            Dashboard
            {isFetching && !isPending && (
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

      <DashboardStatsGrid stats={data?.stats} isPending={isPending} />

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
      >
        <AppointmentStatsCard
          appointmentStats={data?.appointment_stats}
          isPending={isPending}
        />
      </motion.div>

      <div className="grid gap-6 lg:grid-cols-3">
        <motion.div
          className="lg:col-span-2"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <ActiveCampaignsCard
            campaigns={data?.campaign_stats ?? []}
            isPending={isPending}
          />
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <AgentsCard agents={data?.agent_stats ?? []} isPending={isPending} />
        </motion.div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
        >
          <RecentActivityFeed
            activities={data?.recent_activity ?? []}
            isPending={isPending}
          />
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className="space-y-6"
        >
          <TodayOverviewCard
            overview={data?.today_overview}
            isPending={isPending}
          />
          <NudgesCard workspaceId={workspaceId} />
          <QuickActionsCard />
        </motion.div>
      </div>

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
