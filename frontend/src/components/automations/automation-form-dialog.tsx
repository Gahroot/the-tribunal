// Presentational create/edit dialog for automations. Fully controlled: the
// container owns the form state and submit behaviour.
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { AutomationActionType, AutomationTriggerType } from "@/types";

import {
  ACTION_OPTIONS,
  TRIGGER_OPTIONS,
  actionTypeConfig,
  triggerTypeConfig,
} from "./automation-config";
import type { AutomationFormState } from "./automation-logic";

export interface AutomationFormDialogProps {
  open: boolean;
  isEditing: boolean;
  form: AutomationFormState;
  isSubmitting: boolean;
  onFormChange: (patch: Partial<AutomationFormState>) => void;
  onOpenChange: (open: boolean) => void;
  onSubmit: () => void;
  onCancel: () => void;
}

export function AutomationFormDialog({
  open,
  isEditing,
  form,
  isSubmitting,
  onFormChange,
  onOpenChange,
  onSubmit,
  onCancel,
}: AutomationFormDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? "Configure Automation" : "Create Automation"}
          </DialogTitle>
          <DialogDescription>
            {isEditing
              ? "Modify the automation settings"
              : "Set up a new automated workflow"}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="auto-name">Name</Label>
            <Input
              id="auto-name"
              placeholder="e.g., New Lead Welcome"
              value={form.name}
              onChange={(e) => onFormChange({ name: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="auto-desc">Description</Label>
            <Input
              id="auto-desc"
              placeholder="Brief description of what this automation does"
              value={form.description}
              onChange={(e) => onFormChange({ description: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label>Trigger Type</Label>
            <Select
              value={form.triggerType}
              onValueChange={(v) =>
                onFormChange({ triggerType: v as AutomationTriggerType })
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TRIGGER_OPTIONS.map((group) => (
                  <SelectGroup key={group.group}>
                    <SelectLabel>{group.group}</SelectLabel>
                    {group.values.map((value) => {
                      const cfg = triggerTypeConfig[value];
                      const Icon = cfg.icon;
                      return (
                        <SelectItem key={value} value={value}>
                          <div className="flex items-center gap-2">
                            <Icon className={`size-4 ${cfg.color}`} />
                            {cfg.label}
                          </div>
                        </SelectItem>
                      );
                    })}
                  </SelectGroup>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Action</Label>
            <Select
              value={form.actionType}
              onValueChange={(v) =>
                onFormChange({ actionType: v as AutomationActionType })
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ACTION_OPTIONS.map((value) => {
                  const cfg = actionTypeConfig[value];
                  const Icon = cfg.icon;
                  return (
                    <SelectItem key={value} value={value}>
                      <div className="flex items-center gap-2">
                        <Icon className="size-4 text-muted-foreground" />
                        {cfg.label}
                      </div>
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button onClick={onSubmit} disabled={isSubmitting}>
            {isSubmitting && <Loader2 className="mr-2 size-4 animate-spin" />}
            {isEditing ? "Save Changes" : "Create"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
