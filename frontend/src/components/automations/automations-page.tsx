"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Plus,
  Search,
  MoreHorizontal,
  Play,
  Pause,
  Copy,
  Trash2,
  Zap,
  Clock,
  MessageSquare,
  Mail,
  Phone,
  Tag,
  UserCheck,
  ArrowRight,
  Settings2,
} from "lucide-react";

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { Automation, AutomationTriggerType, AutomationActionType } from "@/types";

// Mock data
const mockAutomations: Automation[] = [
  {
    id: "auto-1",
    name: "New Lead Welcome",
    description: "Send welcome SMS to new leads automatically",
    trigger_type: "event",
    trigger_config: { event: "contact_created", status: "new" },
    actions: [
      { type: "send_sms", config: { template: "welcome_sms" } },
      { type: "add_tag", config: { tag: "welcomed" } },
    ],
    is_active: true,
    last_triggered_at: "2024-01-20T10:30:00Z",
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-20T10:30:00Z",
  },
  {
    id: "auto-2",
    name: "Follow-up Reminder",
    description: "Schedule follow-up call 3 days after initial contact",
    trigger_type: "schedule",
    trigger_config: { delay_days: 3, after: "last_contact" },
    actions: [
      { type: "make_call", config: { agent_id: "agent-1" } },
    ],
    is_active: true,
    last_triggered_at: "2024-01-19T14:00:00Z",
    created_at: "2024-01-05T00:00:00Z",
    updated_at: "2024-01-19T14:00:00Z",
  },
  {
    id: "auto-3",
    name: "Hot Lead Assignment",
    description: "Assign hot leads to senior sales agent",
    trigger_type: "condition",
    trigger_config: { field: "status", operator: "equals", value: "qualified" },
    actions: [
      { type: "assign_agent", config: { agent_id: "agent-1" } },
      { type: "send_email", config: { template: "hot_lead_notification" } },
    ],
    is_active: false,
    created_at: "2024-01-10T00:00:00Z",
    updated_at: "2024-01-15T00:00:00Z",
  },
  {
    id: "auto-4",
    name: "Re-engagement Campaign",
    description: "Add inactive contacts to re-engagement campaign",
    trigger_type: "condition",
    trigger_config: { field: "last_activity", operator: "older_than", value: "30_days" },
    actions: [
      { type: "add_tag", config: { tag: "inactive" } },
      { type: "send_sms", config: { template: "reengagement_sms" } },
    ],
    is_active: true,
    last_triggered_at: "2024-01-18T08:00:00Z",
    created_at: "2024-01-08T00:00:00Z",
    updated_at: "2024-01-18T08:00:00Z",
  },
];

const triggerTypeConfig: Record<AutomationTriggerType, { label: string; icon: React.ElementType; color: string }> = {
  event: { label: "Event", icon: Zap, color: "text-yellow-500" },
  schedule: { label: "Schedule", icon: Clock, color: "text-blue-500" },
  condition: { label: "Condition", icon: Settings2, color: "text-purple-500" },
};

const actionTypeConfig: Record<AutomationActionType, { label: string; icon: React.ElementType }> = {
  send_sms: { label: "Send SMS", icon: MessageSquare },
  send_email: { label: "Send Email", icon: Mail },
  make_call: { label: "Make Call", icon: Phone },
  update_status: { label: "Update Status", icon: Settings2 },
  add_tag: { label: "Add Tag", icon: Tag },
  assign_agent: { label: "Assign Agent", icon: UserCheck },
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

export function AutomationsPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);

  const filteredAutomations = mockAutomations.filter(
    (automation) =>
      automation.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      automation.description?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const activeCount = mockAutomations.filter((a) => a.is_active).length;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Automations</h1>
          <p className="text-muted-foreground">
            Create workflows to automate repetitive tasks
          </p>
        </div>
        <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 size-4" />
              Create Automation
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-lg">
            <DialogHeader>
              <DialogTitle>Create Automation</DialogTitle>
              <DialogDescription>
                Set up a new automated workflow
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="auto-name">Name</Label>
                <Input id="auto-name" placeholder="e.g., New Lead Welcome" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="auto-desc">Description</Label>
                <Input
                  id="auto-desc"
                  placeholder="Brief description of what this automation does"
                />
              </div>
              <div className="space-y-2">
                <Label>Trigger Type</Label>
                <Select defaultValue="event">
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="event">
                      <div className="flex items-center gap-2">
                        <Zap className="size-4 text-yellow-500" />
                        Event-based
                      </div>
                    </SelectItem>
                    <SelectItem value="schedule">
                      <div className="flex items-center gap-2">
                        <Clock className="size-4 text-blue-500" />
                        Scheduled
                      </div>
                    </SelectItem>
                    <SelectItem value="condition">
                      <div className="flex items-center gap-2">
                        <Settings2 className="size-4 text-purple-500" />
                        Condition-based
                      </div>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Action</Label>
                <Select defaultValue="send_sms">
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="send_sms">Send SMS</SelectItem>
                    <SelectItem value="send_email">Send Email</SelectItem>
                    <SelectItem value="make_call">Make Call</SelectItem>
                    <SelectItem value="add_tag">Add Tag</SelectItem>
                    <SelectItem value="assign_agent">Assign Agent</SelectItem>
                  </SelectContent>
                </Select>
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
                Create
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Total Automations</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{mockAutomations.length}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Active</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-500">{activeCount}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>Triggered Today</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">24</div>
          </CardContent>
        </Card>
      </div>

      {/* Search */}
      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search automations..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-10"
        />
      </div>

      {/* Automations Grid */}
      <motion.div
        className="grid gap-4 md:grid-cols-2"
        variants={containerVariants}
        initial="hidden"
        animate="visible"
      >
        <AnimatePresence mode="popLayout">
          {filteredAutomations.map((automation) => {
            const trigger = triggerTypeConfig[automation.trigger_type];
            const TriggerIcon = trigger.icon;

            return (
              <motion.div
                key={automation.id}
                layout
                variants={itemVariants}
                initial="hidden"
                animate="visible"
                exit={{ opacity: 0, scale: 0.9 }}
              >
                <Card className="group">
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between">
                      <div className="space-y-1">
                        <CardTitle className="text-lg flex items-center gap-2">
                          {automation.name}
                          {automation.is_active && (
                            <span className="size-2 rounded-full bg-green-500" />
                          )}
                        </CardTitle>
                        <CardDescription>{automation.description}</CardDescription>
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
                          {automation.is_active ? (
                            <DropdownMenuItem>
                              <Pause className="mr-2 size-4" />
                              Pause
                            </DropdownMenuItem>
                          ) : (
                            <DropdownMenuItem>
                              <Play className="mr-2 size-4" />
                              Activate
                            </DropdownMenuItem>
                          )}
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
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {/* Trigger */}
                    <div className="flex items-center gap-3 p-3 rounded-lg bg-muted/50">
                      <div className={`p-2 rounded-md bg-background ${trigger.color}`}>
                        <TriggerIcon className="size-4" />
                      </div>
                      <div className="flex-1">
                        <p className="text-sm font-medium">{trigger.label} Trigger</p>
                        <p className="text-xs text-muted-foreground">
                          {automation.trigger_type === "event" && "When a contact is created"}
                          {automation.trigger_type === "schedule" && "3 days after last contact"}
                          {automation.trigger_type === "condition" && "When status equals qualified"}
                        </p>
                      </div>
                    </div>

                    {/* Arrow */}
                    <div className="flex justify-center">
                      <ArrowRight className="size-4 text-muted-foreground" />
                    </div>

                    {/* Actions */}
                    <div className="space-y-2">
                      {automation.actions.map((action, index) => {
                        const actionConfig = actionTypeConfig[action.type];
                        const ActionIcon = actionConfig.icon;
                        return (
                          <div
                            key={index}
                            className="flex items-center gap-3 p-2 rounded-lg border"
                          >
                            <ActionIcon className="size-4 text-muted-foreground" />
                            <span className="text-sm">{actionConfig.label}</span>
                          </div>
                        );
                      })}
                    </div>
                  </CardContent>
                  <CardFooter className="border-t pt-4">
                    <div className="flex items-center justify-between w-full text-sm">
                      <div className="text-muted-foreground">
                        {automation.last_triggered_at
                          ? `Last run: ${new Date(automation.last_triggered_at).toLocaleDateString()}`
                          : "Never triggered"}
                      </div>
                      <Switch checked={automation.is_active} />
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
