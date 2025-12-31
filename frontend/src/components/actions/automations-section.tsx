"use client";

import * as React from "react";
import { format } from "date-fns";
import { Zap, Clock, Sparkles, AlertCircle, ChevronDown, ChevronUp } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";
import { useContactStore } from "@/lib/contact-store";
import type { Automation } from "@/types";

const triggerIcons: Record<string, React.ReactNode> = {
  schedule: <Clock className="h-4 w-4" />,
  event: <Zap className="h-4 w-4" />,
  condition: <AlertCircle className="h-4 w-4" />,
};

const triggerLabels: Record<string, string> = {
  schedule: "Schedule",
  event: "Event",
  condition: "Condition",
};

const triggerColors: Record<string, string> = {
  schedule: "bg-blue-500/10 text-blue-500",
  event: "bg-amber-500/10 text-amber-500",
  condition: "bg-purple-500/10 text-purple-500",
};

interface AutomationCardProps {
  automation: Automation;
  onToggle: () => void;
}

function AutomationCard({ automation, onToggle }: AutomationCardProps) {
  const [isOpen, setIsOpen] = React.useState(false);

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <motion.div
        layout
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className={cn(
          "rounded-lg border transition-all",
          automation.is_active ? "border-border" : "border-dashed opacity-60"
        )}
      >
        <div className="p-3">
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium text-sm truncate">{automation.name}</span>
                <Badge
                  variant="outline"
                  className={cn("text-xs shrink-0", triggerColors[automation.trigger_type])}
                >
                  {triggerIcons[automation.trigger_type]}
                  <span className="ml-1">{triggerLabels[automation.trigger_type]}</span>
                </Badge>
              </div>
              {automation.description && (
                <p className="text-xs text-muted-foreground line-clamp-1 mt-1">
                  {automation.description}
                </p>
              )}
            </div>

            <Switch
              checked={automation.is_active}
              onCheckedChange={onToggle}
              className="shrink-0"
            />
          </div>

          {automation.last_triggered_at && (
            <div className="flex items-center gap-1.5 mt-2 text-xs text-muted-foreground">
              <Clock className="h-3 w-3" />
              <span>
                Last triggered: {format(new Date(automation.last_triggered_at), "MMM d, h:mm a")}
              </span>
            </div>
          )}
        </div>

        <CollapsibleTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className="w-full h-7 rounded-none border-t text-xs text-muted-foreground hover:text-foreground"
          >
            {isOpen ? (
              <>
                <ChevronUp className="h-3 w-3 mr-1" />
                Hide Actions
              </>
            ) : (
              <>
                <ChevronDown className="h-3 w-3 mr-1" />
                {automation.actions.length} Action{automation.actions.length !== 1 ? "s" : ""}
              </>
            )}
          </Button>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <div className="px-3 pb-3 pt-2 space-y-1.5 border-t bg-muted/30">
            {automation.actions.map((action, index) => (
              <div
                key={index}
                className="flex items-center gap-2 text-xs"
              >
                <div className="h-5 w-5 rounded bg-background flex items-center justify-center text-muted-foreground">
                  {index + 1}
                </div>
                <span className="capitalize">
                  {action.type.replace(/_/g, " ")}
                </span>
              </div>
            ))}
          </div>
        </CollapsibleContent>
      </motion.div>
    </Collapsible>
  );
}

export function AutomationsSection() {
  const { automations, toggleAutomation } = useContactStore();

  const activeCount = automations.filter((a) => a.is_active).length;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Zap className="h-4 w-4 text-amber-500" />
        <h3 className="text-sm font-semibold">Automations</h3>
        <Badge variant="secondary" className="text-xs ml-auto">
          {activeCount} active
        </Badge>
      </div>

      <p className="text-xs text-muted-foreground">
        Automated workflows that trigger based on conditions or schedules.
      </p>

      <AnimatePresence mode="popLayout">
        <div className="space-y-2">
          {automations.map((automation) => (
            <AutomationCard
              key={automation.id}
              automation={automation}
              onToggle={() => toggleAutomation(automation.id)}
            />
          ))}
        </div>
      </AnimatePresence>

      {automations.length === 0 && (
        <div className="text-center py-6 text-sm text-muted-foreground">
          No automations configured yet.
        </div>
      )}
    </div>
  );
}
