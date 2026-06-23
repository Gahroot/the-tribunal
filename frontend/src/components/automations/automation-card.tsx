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
import { Switch } from "@/components/ui/switch";
import { formatDate } from "@/lib/utils/date";
import type { Automation } from "@/types";

import {
  itemVariants,
  resolveActionConfig,
  resolveTriggerConfig,
} from "./automation-config";

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
              <CardTitle className="text-lg flex items-center gap-2">
                {automation.name}
                {automation.is_active && (
                  <span className="size-2 rounded-full bg-success" />
                )}
              </CardTitle>
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
