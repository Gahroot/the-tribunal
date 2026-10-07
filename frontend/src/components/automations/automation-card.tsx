// Presentational automation card + loading skeleton. Stateless: all behaviour
// is delegated to callbacks supplied by the container.
import {
  ArrowRight,
  Copy,
  MoreHorizontal,
  Pause,
  Play,
  Settings2,
  Trash2,
} from "lucide-react";
import { motion } from "motion/react";

import { Button } from "@/components/ui/button";
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
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import { Switch } from "@/components/ui/switch";
import { formatDate } from "@/lib/utils/date";
import type { Automation } from "@/types";

import {
  displayStateConfig,
  itemVariants,
  resolveActionConfig,
  resolveTriggerConfig,
} from "./automation-config";
import { getAutomationDisplayState } from "./automation-logic";

export function AutomationCardSkeleton() {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="space-y-2">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-4 w-60" />
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-10 w-full" />
      </CardContent>
      <CardFooter className="border-t pt-4">
        <Skeleton className="h-4 w-full" />
      </CardFooter>
    </Card>
  );
}

export interface AutomationCardProps {
  automation: Automation;
  onConfigure: (automation: Automation) => void;
  onToggle: (automation: Automation) => void;
  onDuplicate: (automation: Automation) => void;
  onDelete: (automation: Automation) => void;
  isToggling: boolean;
  isDuplicating: boolean;
  isDeleting: boolean;
}

export function AutomationCard({
  automation,
  onConfigure,
  onToggle,
  onDuplicate,
  onDelete,
  isToggling,
  isDuplicating,
  isDeleting,
}: AutomationCardProps) {
  const trigger = resolveTriggerConfig(automation.trigger_type);
  const TriggerIcon = trigger.icon;
  const displayState = getAutomationDisplayState(automation);
  const status = displayStateConfig[displayState];
  const lastError =
    automation.last_execution?.status === "failed"
      ? automation.last_execution.error
      : null;

  return (
    <motion.div
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
              <CardTitle className="text-lg">{automation.name}</CardTitle>
              <StatusBadge dotClass={status.dotClass}>{status.label}</StatusBadge>
              <CardDescription>{automation.description}</CardDescription>
            </div>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-8 opacity-0 group-hover:opacity-100"
                  aria-label="Automation actions"
                >
                  <MoreHorizontal className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => onConfigure(automation)}>
                  <Settings2 className="mr-2 size-4" />
                  Configure
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => onToggle(automation)}
                  disabled={isToggling}
                >
                  {automation.is_active ? (
                    <>
                      <Pause className="mr-2 size-4" />
                      Pause
                    </>
                  ) : (
                    <>
                      <Play className="mr-2 size-4" />
                      Activate
                    </>
                  )}
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => onDuplicate(automation)}
                  disabled={isDuplicating}
                >
                  <Copy className="mr-2 size-4" />
                  Duplicate
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className="text-destructive"
                  onClick={() => onDelete(automation)}
                  disabled={isDeleting}
                >
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
                {trigger.description}
              </p>
            </div>
          </div>

          {/* Arrow */}
          <div className="flex justify-center">
            <ArrowRight className="size-4 text-muted-foreground" />
          </div>

          {displayState === "incomplete" && automation.config_issues.length > 0 && (
            <div className="rounded-lg border border-warning/40 p-3 text-sm">
              <p className="font-medium">Finish setup to activate</p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-muted-foreground">
                {automation.config_issues.map((issue) => (
                  <li key={`${issue.field}-${issue.code}`}>{issue.message}</li>
                ))}
              </ul>
              <Button
                variant="link"
                size="sm"
                className="h-auto px-0"
                onClick={() => onConfigure(automation)}
              >
                Configure
              </Button>
            </div>
          )}

          {lastError && (
            <div
              role="status"
              className="rounded-lg border border-destructive/40 p-3 text-sm"
            >
              <p className="font-medium">Last run failed</p>
              <p className="text-muted-foreground">{lastError}</p>
            </div>
          )}

          {/* Actions */}
          <div className="space-y-2">
            {automation.actions.map((action, index) => {
              const actionConfig = resolveActionConfig(action.type);
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
                ? `Last run: ${formatDate(automation.last_triggered_at)}`
                : "Never triggered"}
            </div>
            <Switch
              aria-label={automation.is_active ? "Pause automation" : "Activate automation"}
              checked={automation.is_active}
              onCheckedChange={() => onToggle(automation)}
              disabled={isToggling}
            />
          </div>
        </CardFooter>
      </Card>
    </motion.div>
  );
}
