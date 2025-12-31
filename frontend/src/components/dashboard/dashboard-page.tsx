"use client";

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
  Bot,
} from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

// Mock data
const stats = [
  {
    title: "Total Contacts",
    value: "2,543",
    change: "+12%",
    trend: "up",
    icon: Users,
    href: "/",
  },
  {
    title: "Active Campaigns",
    value: "8",
    change: "+2",
    trend: "up",
    icon: Megaphone,
    href: "/campaigns",
  },
  {
    title: "Calls Today",
    value: "156",
    change: "+23%",
    trend: "up",
    icon: Phone,
    href: "/calls",
  },
  {
    title: "Messages Sent",
    value: "1,234",
    change: "-5%",
    trend: "down",
    icon: MessageSquare,
    href: "/campaigns",
  },
];

const recentActivity = [
  {
    id: 1,
    type: "call",
    contact: "John Smith",
    initials: "JS",
    action: "completed call",
    time: "5 min ago",
    duration: "4:32",
  },
  {
    id: 2,
    type: "sms",
    contact: "Emily Johnson",
    initials: "EJ",
    action: "replied to SMS",
    time: "12 min ago",
  },
  {
    id: 3,
    type: "campaign",
    contact: "Spring Campaign",
    initials: "SC",
    action: "reached 1,000 contacts",
    time: "1 hour ago",
  },
  {
    id: 4,
    type: "call",
    contact: "Michael Brown",
    initials: "MB",
    action: "missed call",
    time: "2 hours ago",
  },
  {
    id: 5,
    type: "booking",
    contact: "Sarah Wilson",
    initials: "SW",
    action: "booked appointment",
    time: "3 hours ago",
  },
];

const activeCampaigns = [
  {
    id: "1",
    name: "Spring Property Showcase",
    type: "sms",
    progress: 71,
    sent: 890,
    total: 1250,
    status: "running",
  },
  {
    id: "2",
    name: "Follow-up Calls",
    type: "voice",
    progress: 43,
    sent: 87,
    total: 200,
    status: "running",
  },
  {
    id: "3",
    name: "Email Nurture",
    type: "email",
    progress: 25,
    sent: 125,
    total: 500,
    status: "scheduled",
  },
];

const topAgents = [
  { name: "Sarah", calls: 245, successRate: 92 },
  { name: "Mike", calls: 189, successRate: 88 },
  { name: "Emma", calls: 156, successRate: 95 },
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

export function DashboardPage() {
  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-muted-foreground">
            Welcome back! Here's an overview of your CRM activity.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" asChild>
            <Link href="/campaigns/new">New Campaign</Link>
          </Button>
          <Button asChild>
            <Link href="/">
              <Users className="mr-2 size-4" />
              View Contacts
            </Link>
          </Button>
        </div>
      </div>

      {/* Stats Grid */}
      <motion.div
        className="grid gap-4 md:grid-cols-2 lg:grid-cols-4"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        {stats.map((stat) => (
          <motion.div key={stat.title} variants={itemVariants}>
            <Link href={stat.href}>
              <Card className="hover:bg-muted/50 transition-colors cursor-pointer">
                <CardHeader className="flex flex-row items-center justify-between pb-2">
                  <CardDescription>{stat.title}</CardDescription>
                  <stat.icon className="size-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="flex items-center justify-between">
                    <div className="text-2xl font-bold">{stat.value}</div>
                    <div
                      className={`flex items-center text-sm ${
                        stat.trend === "up"
                          ? "text-green-500"
                          : "text-red-500"
                      }`}
                    >
                      {stat.trend === "up" ? (
                        <TrendingUp className="mr-1 size-4" />
                      ) : (
                        <TrendingDown className="mr-1 size-4" />
                      )}
                      {stat.change}
                    </div>
                  </div>
                </CardContent>
              </Card>
            </Link>
          </motion.div>
        ))}
      </motion.div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Active Campaigns */}
        <motion.div
          className="lg:col-span-2"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Active Campaigns</CardTitle>
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
              {activeCampaigns.map((campaign) => (
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
                              ? "bg-green-500/10 text-green-500 border-green-500/20"
                              : "bg-blue-500/10 text-blue-500 border-blue-500/20"
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
              ))}
            </CardContent>
          </Card>
        </motion.div>

        {/* AI Agents Performance */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bot className="size-5" />
                AI Agents
              </CardTitle>
              <CardDescription>Performance this week</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {topAgents.map((agent, index) => (
                <div
                  key={agent.name}
                  className="flex items-center justify-between"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex size-8 items-center justify-center rounded-full bg-primary/10 text-sm font-medium">
                      {index + 1}
                    </div>
                    <div>
                      <p className="font-medium">{agent.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {agent.calls} calls
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="font-medium text-green-500">
                      {agent.successRate}%
                    </p>
                    <p className="text-xs text-muted-foreground">success</p>
                  </div>
                </div>
              ))}
              <Button variant="outline" className="w-full" asChild>
                <Link href="/agents">
                  Manage Agents
                </Link>
              </Button>
            </CardContent>
          </Card>
        </motion.div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Recent Activity */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
        >
          <Card>
            <CardHeader>
              <CardTitle>Recent Activity</CardTitle>
              <CardDescription>Latest interactions and updates</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {recentActivity.map((activity) => (
                <div
                  key={activity.id}
                  className="flex items-center gap-4 text-sm"
                >
                  <Avatar className="size-9">
                    <AvatarFallback className="text-xs">
                      {activity.initials}
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex-1">
                    <p>
                      <span className="font-medium">{activity.contact}</span>{" "}
                      <span className="text-muted-foreground">
                        {activity.action}
                      </span>
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {activity.time}
                      {activity.duration && ` • ${activity.duration}`}
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
              ))}
            </CardContent>
          </Card>
        </motion.div>

        {/* Quick Actions & Metrics */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.5 }}
          className="space-y-6"
        >
          {/* Today's Overview */}
          <Card>
            <CardHeader>
              <CardTitle>Today's Overview</CardTitle>
              <CardDescription>Key metrics for today</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-4 text-center">
                <div className="space-y-1">
                  <div className="flex items-center justify-center gap-1 text-green-500">
                    <CheckCircle className="size-4" />
                    <span className="text-2xl font-bold">89</span>
                  </div>
                  <p className="text-xs text-muted-foreground">Completed</p>
                </div>
                <div className="space-y-1">
                  <div className="flex items-center justify-center gap-1 text-yellow-500">
                    <Clock className="size-4" />
                    <span className="text-2xl font-bold">23</span>
                  </div>
                  <p className="text-xs text-muted-foreground">Pending</p>
                </div>
                <div className="space-y-1">
                  <div className="flex items-center justify-center gap-1 text-red-500">
                    <XCircle className="size-4" />
                    <span className="text-2xl font-bold">5</span>
                  </div>
                  <p className="text-xs text-muted-foreground">Failed</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Quick Actions */}
          <Card>
            <CardHeader>
              <CardTitle>Quick Actions</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-2">
              <Button variant="outline" className="justify-start" asChild>
                <Link href="/campaigns/new">
                  <Megaphone className="mr-2 size-4" />
                  New Campaign
                </Link>
              </Button>
              <Button variant="outline" className="justify-start" asChild>
                <Link href="/">
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
        </motion.div>
      </div>
    </div>
  );
}
