// Presentational create/edit dialog for automations. Fully controlled: the
// container owns the form state and submit behaviour. Collects the settings
// each trigger/action actually needs, with defaults and inline guidance.
import { Loader2, Trash2 } from "lucide-react";

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
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import type { AutomationActionType, AutomationTriggerType } from "@/types";

import {
  ACTION_GUIDANCE,
  ACTION_OPTIONS,
  TEMPLATE_TOKENS_HINT,
  TRIGGER_GUIDANCE,
  TRIGGER_OPTIONS,
  resolveActionConfig,
  resolveTriggerConfig,
} from "./automation-config";
import {
  type AutomationFormState,
  type FormIssue,
  changeActionType,
  changeTrigger,
  issuesFor,
  removeAction,
  setActionField,
  setTriggerField,
} from "./automation-logic";

const DEFAULT_AGENT = "__default__";

export interface AutomationOption {
  id: string;
  name: string;
  /** Extra context shown beside the name, e.g. a campaign's status. */
  hint?: string;
}

export interface AutomationFormDialogProps {
  open: boolean;
  isEditing: boolean;
  form: AutomationFormState;
  /** Reasons the automation could not run yet (shown inline). */
  issues: FormIssue[];
  campaigns: AutomationOption[];
  agents: AutomationOption[];
  isSubmitting: boolean;
  onFormChange: (patch: Partial<AutomationFormState>) => void;
  onOpenChange: (open: boolean) => void;
  onSubmit: () => void;
  onCancel: () => void;
}

function FieldMessages({ id, messages }: { id: string; messages: string[] }) {
  if (messages.length === 0) return null;
  return (
    <div id={id} className="space-y-0.5">
      {messages.map((message) => (
        <p key={message} className="text-xs text-destructive">
          {message}
        </p>
      ))}
    </div>
  );
}

function Hint({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-muted-foreground">{children}</p>;
}

const asText = (value: unknown): string =>
  typeof value === "string" || typeof value === "number" ? String(value) : "";

export function AutomationFormDialog({
  open,
  isEditing,
  form,
  issues,
  campaigns,
  agents,
  isSubmitting,
  onFormChange,
  onOpenChange,
  onSubmit,
  onCancel,
}: AutomationFormDialogProps) {
  const offeredTriggers = TRIGGER_OPTIONS.flatMap((group) => group.values);
  const triggerIsLegacy = !offeredTriggers.includes(form.triggerType);
  const triggerTagErrors = issuesFor(issues, "trigger_config.tag");
  const inactivityErrors = issuesFor(issues, "trigger_config.inactivity_days");
  const triggerTypeErrors = issuesFor(issues, "trigger_type");
  const canRemoveSteps = form.actions.length > 1;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? "Configure Automation" : "Create Automation"}
          </DialogTitle>
          <DialogDescription>
            Choose what starts the automation and what it does. Active
            automations must be fully set up; switch off &quot;Active&quot; to
            save a draft.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-5 py-2">
          <div className="space-y-2">
            <Label htmlFor="auto-name">Name</Label>
            <Input
              id="auto-name"
              placeholder="e.g., No-show follow-up"
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

          {/* Trigger */}
          <fieldset className="space-y-2">
            <Label htmlFor="auto-trigger">When this happens</Label>
            <Select
              value={form.triggerType}
              onValueChange={(v) =>
                onFormChange(changeTrigger(form, v as AutomationTriggerType))
              }
            >
              <SelectTrigger
                id="auto-trigger"
                aria-invalid={triggerTypeErrors.length > 0}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {triggerIsLegacy && (
                  <SelectGroup>
                    <SelectLabel>Current (not supported)</SelectLabel>
                    <SelectItem value={form.triggerType}>
                      {resolveTriggerConfig(form.triggerType).label}
                    </SelectItem>
                  </SelectGroup>
                )}
                {TRIGGER_OPTIONS.map((group) => (
                  <SelectGroup key={group.group}>
                    <SelectLabel>{group.group}</SelectLabel>
                    {group.values.map((value) => {
                      const cfg = resolveTriggerConfig(value);
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
            {TRIGGER_GUIDANCE[form.triggerType] && (
              <Hint>{TRIGGER_GUIDANCE[form.triggerType]}</Hint>
            )}
            <FieldMessages id="auto-trigger-errors" messages={triggerTypeErrors} />

            {form.triggerType === "contact_tagged" && (
              <div className="space-y-1 pt-1">
                <Label htmlFor="auto-trigger-tag">Tag</Label>
                <Input
                  id="auto-trigger-tag"
                  placeholder="e.g., hot-lead"
                  value={asText(form.triggerConfig.tag)}
                  aria-invalid={triggerTagErrors.length > 0}
                  aria-describedby="auto-trigger-tag-errors"
                  onChange={(e) =>
                    onFormChange(setTriggerField(form, "tag", e.target.value))
                  }
                />
                <FieldMessages
                  id="auto-trigger-tag-errors"
                  messages={triggerTagErrors}
                />
              </div>
            )}
            {form.triggerType === "never_booked" && (
              <div className="space-y-1 pt-1">
                <Label htmlFor="auto-inactivity">Days without booking</Label>
                <Input
                  id="auto-inactivity"
                  type="number"
                  min={1}
                  max={365}
                  value={asText(form.triggerConfig.inactivity_days)}
                  aria-invalid={inactivityErrors.length > 0}
                  aria-describedby="auto-inactivity-errors"
                  onChange={(e) =>
                    onFormChange(
                      setTriggerField(
                        form,
                        "inactivity_days",
                        e.target.value === "" ? "" : Number(e.target.value),
                      ),
                    )
                  }
                />
                <FieldMessages
                  id="auto-inactivity-errors"
                  messages={inactivityErrors}
                />
              </div>
            )}
          </fieldset>

          {/* Actions */}
          {form.actions.map((action, index) => {
            const prefix = `actions[${index}]`;
            const config = action.config ?? {};
            const typeErrors = issuesFor(issues, `${prefix}.type`);
            const fieldErrors = (key: string) =>
              issuesFor(issues, `${prefix}.config.${key}`);
            const idBase = `auto-action-${index}`;
            const isLegacyAction = !ACTION_OPTIONS.includes(action.type);
            return (
              <fieldset
                key={index}
                className="space-y-2 rounded-lg border p-3"
                aria-label={`Step ${index + 1}`}
              >
                <div className="flex items-center justify-between">
                  <Label htmlFor={`${idBase}-type`}>
                    {index === 0 ? "Do this" : `Then (step ${index + 1})`}
                  </Label>
                  {canRemoveSteps && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      className="size-7"
                      aria-label={`Remove step ${index + 1}`}
                      onClick={() => onFormChange(removeAction(form, index))}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  )}
                </div>
                <Select
                  value={action.type}
                  onValueChange={(v) =>
                    onFormChange(
                      changeActionType(form, index, v as AutomationActionType),
                    )
                  }
                >
                  <SelectTrigger
                    id={`${idBase}-type`}
                    aria-invalid={typeErrors.length > 0}
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {isLegacyAction && (
                      <SelectItem value={action.type}>
                        {resolveActionConfig(action.type).label} (not supported)
                      </SelectItem>
                    )}
                    {ACTION_OPTIONS.map((value) => {
                      const cfg = resolveActionConfig(value);
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
                {ACTION_GUIDANCE[action.type] && (
                  <Hint>{ACTION_GUIDANCE[action.type]}</Hint>
                )}
                <FieldMessages id={`${idBase}-type-errors`} messages={typeErrors} />

                {action.type === "send_sms" && (
                  <div className="space-y-1">
                    <Label htmlFor={`${idBase}-message`}>Message</Label>
                    <Textarea
                      id={`${idBase}-message`}
                      rows={3}
                      value={asText(config.message)}
                      aria-invalid={fieldErrors("message").length > 0}
                      aria-describedby={`${idBase}-message-errors`}
                      onChange={(e) =>
                        onFormChange(
                          setActionField(form, index, "message", e.target.value),
                        )
                      }
                    />
                    <Hint>{TEMPLATE_TOKENS_HINT}</Hint>
                    <FieldMessages
                      id={`${idBase}-message-errors`}
                      messages={fieldErrors("message")}
                    />
                  </div>
                )}

                {action.type === "send_email" && (
                  <>
                    <div className="space-y-1">
                      <Label htmlFor={`${idBase}-subject`}>Subject</Label>
                      <Input
                        id={`${idBase}-subject`}
                        value={asText(config.subject)}
                        aria-invalid={fieldErrors("subject").length > 0}
                        aria-describedby={`${idBase}-subject-errors`}
                        onChange={(e) =>
                          onFormChange(
                            setActionField(form, index, "subject", e.target.value),
                          )
                        }
                      />
                      <FieldMessages
                        id={`${idBase}-subject-errors`}
                        messages={fieldErrors("subject")}
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor={`${idBase}-body`}>Body</Label>
                      <Textarea
                        id={`${idBase}-body`}
                        rows={4}
                        value={asText(config.message ?? config.body)}
                        aria-invalid={fieldErrors("message").length > 0}
                        aria-describedby={`${idBase}-body-errors`}
                        onChange={(e) =>
                          onFormChange(
                            setActionField(form, index, "message", e.target.value),
                          )
                        }
                      />
                      <Hint>{TEMPLATE_TOKENS_HINT}</Hint>
                      <FieldMessages
                        id={`${idBase}-body-errors`}
                        messages={fieldErrors("message")}
                      />
                    </div>
                  </>
                )}

                {action.type === "make_call" && (
                  <div className="space-y-1">
                    <Label htmlFor={`${idBase}-agent`}>Voice agent</Label>
                    <Select
                      value={asText(config.agent_id) || DEFAULT_AGENT}
                      onValueChange={(v) =>
                        onFormChange(
                          setActionField(
                            form,
                            index,
                            "agent_id",
                            v === DEFAULT_AGENT ? undefined : v,
                          ),
                        )
                      }
                    >
                      <SelectTrigger
                        id={`${idBase}-agent`}
                        aria-invalid={fieldErrors("agent_id").length > 0}
                      >
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={DEFAULT_AGENT}>
                          Default call handling
                        </SelectItem>
                        {agents.map((agent) => (
                          <SelectItem key={agent.id} value={agent.id}>
                            {agent.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FieldMessages
                      id={`${idBase}-agent-errors`}
                      messages={fieldErrors("agent_id")}
                    />
                  </div>
                )}

                {action.type === "enroll_campaign" && (
                  <div className="space-y-1">
                    <Label htmlFor={`${idBase}-campaign`}>Campaign</Label>
                    <Select
                      value={asText(config.campaign_id) || undefined}
                      onValueChange={(v) =>
                        onFormChange(setActionField(form, index, "campaign_id", v))
                      }
                    >
                      <SelectTrigger
                        id={`${idBase}-campaign`}
                        aria-invalid={fieldErrors("campaign_id").length > 0}
                        aria-describedby={`${idBase}-campaign-errors`}
                      >
                        <SelectValue placeholder="Choose a campaign" />
                      </SelectTrigger>
                      <SelectContent>
                        {campaigns.length === 0 && (
                          <div className="px-2 py-1.5 text-sm text-muted-foreground">
                            No campaigns yet. Create one under Campaigns.
                          </div>
                        )}
                        {campaigns.map((campaign) => (
                          <SelectItem key={campaign.id} value={campaign.id}>
                            {campaign.name}
                            {campaign.hint ? ` (${campaign.hint})` : ""}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FieldMessages
                      id={`${idBase}-campaign-errors`}
                      messages={fieldErrors("campaign_id")}
                    />
                  </div>
                )}

                {(action.type === "apply_tag" || action.type === "add_tag") && (
                  <div className="space-y-1">
                    <Label htmlFor={`${idBase}-tag`}>Tag</Label>
                    <Input
                      id={`${idBase}-tag`}
                      placeholder="e.g., no-show-followed-up"
                      value={asText(config.tag)}
                      aria-invalid={fieldErrors("tag").length > 0}
                      aria-describedby={`${idBase}-tag-errors`}
                      onChange={(e) =>
                        onFormChange(setActionField(form, index, "tag", e.target.value))
                      }
                    />
                    <FieldMessages
                      id={`${idBase}-tag-errors`}
                      messages={fieldErrors("tag")}
                    />
                  </div>
                )}
              </fieldset>
            );
          })}
          <FieldMessages id="auto-actions-errors" messages={issuesFor(issues, "actions")} />

          <div className="flex items-start justify-between gap-4 rounded-lg border p-3">
            <div className="space-y-0.5">
              <Label htmlFor="auto-active">Active</Label>
              <Hint>
                {form.isActive
                  ? "Runs automatically once saved. Requires every field above."
                  : "Saved as a draft. Nothing runs until you activate it."}
              </Hint>
            </div>
            <Switch
              id="auto-active"
              checked={form.isActive}
              onCheckedChange={(checked) => onFormChange({ isActive: checked })}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button onClick={onSubmit} disabled={isSubmitting}>
            {isSubmitting && <Loader2 className="mr-2 size-4 animate-spin" />}
            {isEditing ? "Save Changes" : form.isActive ? "Create" : "Save Draft"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
