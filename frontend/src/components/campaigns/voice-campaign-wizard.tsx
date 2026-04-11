"use client";

import { useMemo, useState } from "react";
import {
  AlertCircle,
  Clock,
  Eye,
  FileText,
  MessageSquare,
  Phone,
  Users,
} from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";

import { AgentSelector } from "./agent-selector";
import { BaseCampaignWizard } from "./base-campaign-wizard";
import { SMSFallbackStep, type SMSFallbackMode } from "./sms-fallback-step";
import {
  BasicsStep,
  ContactsStep,
  ReviewScheduleCard,
  ReviewSummaryCard,
  ScheduleStep,
} from "./steps";
import type { WizardStep } from "./wizard-types";

import type { CreateVoiceCampaignRequest } from "@/lib/api/voice-campaigns";
import type { Agent, PhoneNumber, VoiceCampaign } from "@/types";

type StepId =
  | "basics"
  | "contacts"
  | "voice"
  | "fallback"
  | "schedule"
  | "review";

interface VoiceCampaignWizardProps {
  workspaceId: string;
  voiceAgents: Agent[];
  textAgents: Agent[];
  phoneNumbers: PhoneNumber[];
  onSubmit: (
    data: CreateVoiceCampaignRequest,
    contactIds: Set<number>
  ) => Promise<VoiceCampaign>;
  onCancel?: () => void;
  isSubmitting?: boolean;
}

interface VoiceFormData {
  name: string;
  description: string;
  from_phone_number: string;
  voice_agent_id?: string;
  enable_machine_detection: boolean;
  max_call_duration_seconds: number;
  sms_fallback_enabled: boolean;
  sms_fallback_mode: SMSFallbackMode;
  sms_fallback_template: string;
  sms_fallback_agent_id?: string;
  ai_enabled: boolean;
  qualification_criteria: string;
  scheduled_start?: string;
  scheduled_end?: string;
  sending_hours_enabled: boolean;
  sending_hours_start: string;
  sending_hours_end: string;
  sending_days: number[];
  timezone: string;
  calls_per_minute: number;
}

const initialFormData: VoiceFormData = {
  name: "",
  description: "",
  from_phone_number: "",
  voice_agent_id: undefined,
  enable_machine_detection: true,
  max_call_duration_seconds: 120,
  sms_fallback_enabled: true,
  sms_fallback_mode: "template",
  sms_fallback_template:
    "Hi {first_name}, {call_reason} - reply to this message or call us back at your convenience.",
  sms_fallback_agent_id: undefined,
  ai_enabled: true,
  qualification_criteria: "",
  sending_hours_enabled: true,
  sending_hours_start: "09:00",
  sending_hours_end: "17:00",
  sending_days: [1, 2, 3, 4, 5],
  timezone: "America/New_York",
  calls_per_minute: 5,
};

export function VoiceCampaignWizard({
  workspaceId,
  voiceAgents,
  textAgents,
  phoneNumbers,
  onSubmit,
  onCancel,
  isSubmitting = false,
}: VoiceCampaignWizardProps) {
  const [selectedContactIds, setSelectedContactIds] = useState<Set<number>>(
    new Set()
  );

  const steps = useMemo<ReadonlyArray<WizardStep<StepId, VoiceFormData>>>(
    () => [
      {
        id: "basics",
        label: "Basics",
        icon: FileText,
        validate: (data) => {
          const errors: Record<string, string> = {};
          if (!data.name.trim()) errors.name = "Campaign name is required";
          if (!data.from_phone_number)
            errors.from_phone_number = "Phone number is required";
          return errors;
        },
        render: ({ formData, errors, updateField }) => (
          <BasicsStep
            name={formData.name}
            description={formData.description}
            fromPhoneNumber={formData.from_phone_number}
            phoneNumbers={phoneNumbers}
            errors={errors}
            onNameChange={(v) => updateField("name", v)}
            onDescriptionChange={(v) => updateField("description", v)}
            onPhoneChange={(v) => updateField("from_phone_number", v)}
            namePlaceholder="e.g., Follow-up Calls - January"
            emptyPhoneLabel="No voice-enabled phone numbers available"
          />
        ),
      },
      {
        id: "contacts",
        label: "Contacts",
        icon: Users,
        validate: () =>
          selectedContactIds.size === 0
            ? { contacts: "Select at least one contact" }
            : {},
        render: ({ errors }) => (
          <ContactsStep
            workspaceId={workspaceId}
            selectedIds={selectedContactIds}
            onSelectionChange={setSelectedContactIds}
            error={errors.contacts}
          />
        ),
      },
      {
        id: "voice",
        label: "Voice Agent",
        icon: Phone,
        validate: (data) =>
          !data.voice_agent_id
            ? { voice_agent_id: "Voice agent is required" }
            : {},
        render: ({ formData, errors, updateField }) => (
          <div className="space-y-6">
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
                <Phone className="size-4" />
                <span>Select the AI agent that will handle voice calls</span>
              </div>

              {errors.voice_agent_id && (
                <Alert variant="destructive">
                  <AlertCircle className="size-4" />
                  <AlertDescription>{errors.voice_agent_id}</AlertDescription>
                </Alert>
              )}

              <AgentSelector
                agents={voiceAgents}
                selectedId={formData.voice_agent_id}
                onSelect={(id) => updateField("voice_agent_id", id)}
                showVoiceAgentsOnly={true}
                allowNone={false}
              />
            </div>

            <Separator />

            <div className="space-y-4">
              <h4 className="font-medium">Call Settings</h4>

              <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
                <div>
                  <h5 className="font-medium">Machine Detection</h5>
                  <p className="text-sm text-muted-foreground">
                    Detect voicemail and hang up automatically
                  </p>
                </div>
                <Switch
                  checked={formData.enable_machine_detection}
                  onCheckedChange={(v) =>
                    updateField("enable_machine_detection", v)
                  }
                />
              </div>

              <div className="space-y-2">
                <Label>Max Call Duration</Label>
                <Select
                  value={String(formData.max_call_duration_seconds)}
                  onValueChange={(v) =>
                    updateField("max_call_duration_seconds", parseInt(v))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="60">1 minute</SelectItem>
                    <SelectItem value="120">2 minutes</SelectItem>
                    <SelectItem value="180">3 minutes</SelectItem>
                    <SelectItem value="300">5 minutes</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
        ),
      },
      {
        id: "fallback",
        label: "SMS Fallback",
        icon: MessageSquare,
        validate: (data) => {
          if (!data.sms_fallback_enabled) return {};
          const errors: Record<string, string> = {};
          if (
            data.sms_fallback_mode === "template" &&
            !data.sms_fallback_template.trim()
          ) {
            errors.template = "Fallback template is required";
          }
          if (
            data.sms_fallback_mode === "ai" &&
            !data.sms_fallback_agent_id
          ) {
            errors.agentId = "Select an agent for AI-generated messages";
          }
          return errors;
        },
        render: ({ formData, errors, updateField }) => (
          <SMSFallbackStep
            enabled={formData.sms_fallback_enabled}
            onEnabledChange={(v) => updateField("sms_fallback_enabled", v)}
            mode={formData.sms_fallback_mode}
            onModeChange={(v) => updateField("sms_fallback_mode", v)}
            template={formData.sms_fallback_template}
            onTemplateChange={(v) => updateField("sms_fallback_template", v)}
            agentId={formData.sms_fallback_agent_id}
            onAgentChange={(v) => updateField("sms_fallback_agent_id", v)}
            agents={textAgents}
            errors={errors}
          />
        ),
      },
      {
        id: "schedule",
        label: "Schedule",
        icon: Clock,
        validate: (data) =>
          data.sending_days.length === 0
            ? { sending_days: "Select at least one day" }
            : {},
        render: ({ formData, errors, updateField }) => (
          <ScheduleStep
            scheduledStart={formData.scheduled_start}
            scheduledEnd={formData.scheduled_end}
            sendingHoursEnabled={formData.sending_hours_enabled}
            sendingHoursStart={formData.sending_hours_start}
            sendingHoursEnd={formData.sending_hours_end}
            sendingDays={formData.sending_days}
            timezone={formData.timezone}
            errors={errors}
            onScheduledStartChange={(v) => updateField("scheduled_start", v)}
            onScheduledEndChange={(v) => updateField("scheduled_end", v)}
            onSendingHoursEnabledChange={(v) =>
              updateField("sending_hours_enabled", v)
            }
            onSendingHoursStartChange={(v) =>
              updateField("sending_hours_start", v)
            }
            onSendingHoursEndChange={(v) =>
              updateField("sending_hours_end", v)
            }
            onSendingDaysChange={(v) => updateField("sending_days", v)}
            onTimezoneChange={(v) => updateField("timezone", v)}
            sendingHoursLabel="Restrict Calling Hours"
            sendingHoursDescription="Only make calls during specific hours"
            daysLabel="Calling Days"
            rateLimitingSlot={
              <div className="space-y-4">
                <h4 className="font-medium">Rate Limiting</h4>
                <div className="space-y-2">
                  <Label>Calls per Minute</Label>
                  <Select
                    value={String(formData.calls_per_minute)}
                    onValueChange={(v) =>
                      updateField("calls_per_minute", parseInt(v))
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="1">1 / minute</SelectItem>
                      <SelectItem value="3">3 / minute</SelectItem>
                      <SelectItem value="5">5 / minute</SelectItem>
                      <SelectItem value="10">10 / minute</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    Lower rates are recommended to avoid overwhelming your
                    agents
                  </p>
                </div>
              </div>
            }
          />
        ),
      },
      {
        id: "review",
        label: "Review",
        icon: Eye,
        render: ({ formData }) => {
          const selectedVoiceAgent = voiceAgents.find(
            (a) => a.id === formData.voice_agent_id
          );
          const selectedFallbackAgent = textAgents.find(
            (a) => a.id === formData.sms_fallback_agent_id
          );
          const selectedPhone = phoneNumbers.find(
            (p) => p.phone_number === formData.from_phone_number
          );
          return (
            <div className="space-y-6">
              <ReviewSummaryCard
                name={formData.name}
                description={formData.description || undefined}
                fromPhoneDisplay={
                  selectedPhone?.friendly_name || formData.from_phone_number
                }
              />

              <Card>
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Users className="size-5" />
                    Recipients
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="text-lg px-3 py-1">
                      {selectedContactIds.size}
                    </Badge>
                    <span className="text-muted-foreground">
                      contacts will receive calls
                    </span>
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Phone className="size-5" />
                    Voice Agent
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {selectedVoiceAgent && (
                    <Badge variant="default">{selectedVoiceAgent.name}</Badge>
                  )}
                  <div className="text-sm text-muted-foreground">
                    Machine detection:{" "}
                    {formData.enable_machine_detection
                      ? "Enabled"
                      : "Disabled"}
                  </div>
                  <div className="text-sm text-muted-foreground">
                    Max call duration:{" "}
                    {formData.max_call_duration_seconds / 60} minute(s)
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <MessageSquare className="size-5" />
                    SMS Fallback
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {formData.sms_fallback_enabled ? (
                    <div className="space-y-2">
                      <Badge
                        variant="secondary"
                        className="bg-success/10 text-success"
                      >
                        {formData.sms_fallback_mode === "ai"
                          ? "AI-Generated"
                          : "Template"}
                      </Badge>
                      {formData.sms_fallback_mode === "ai" &&
                        selectedFallbackAgent && (
                          <p className="text-sm text-muted-foreground">
                            Using agent: {selectedFallbackAgent.name}
                          </p>
                        )}
                      {formData.sms_fallback_mode === "template" && (
                        <p className="text-sm text-muted-foreground line-clamp-2">
                          {formData.sms_fallback_template}
                        </p>
                      )}
                    </div>
                  ) : (
                    <p className="text-muted-foreground">
                      SMS fallback is disabled
                    </p>
                  )}
                </CardContent>
              </Card>

              <ReviewScheduleCard
                sendingHoursEnabled={formData.sending_hours_enabled}
                sendingHoursStart={formData.sending_hours_start}
                sendingHoursEnd={formData.sending_hours_end}
                sendingDays={formData.sending_days}
                timezone={formData.timezone}
                hoursLabel="Calling hours"
                rateDescription={<>{formData.calls_per_minute} calls/min</>}
              />
            </div>
          );
        },
      },
    ],
    [
      workspaceId,
      voiceAgents,
      textAgents,
      phoneNumbers,
      selectedContactIds,
    ]
  );

  const handleSubmit = async (formData: VoiceFormData) => {
    const request: CreateVoiceCampaignRequest = {
      name: formData.name,
      description: formData.description || undefined,
      from_phone_number: formData.from_phone_number,
      voice_agent_id: formData.voice_agent_id!,
      enable_machine_detection: formData.enable_machine_detection,
      max_call_duration_seconds: formData.max_call_duration_seconds,
      sms_fallback_enabled: formData.sms_fallback_enabled,
      sms_fallback_template:
        formData.sms_fallback_mode === "template"
          ? formData.sms_fallback_template
          : undefined,
      sms_fallback_use_ai: formData.sms_fallback_mode === "ai",
      sms_fallback_agent_id:
        formData.sms_fallback_mode === "ai"
          ? formData.sms_fallback_agent_id
          : undefined,
      ai_enabled: formData.ai_enabled,
      qualification_criteria: formData.qualification_criteria || undefined,
      scheduled_start: formData.scheduled_start || undefined,
      scheduled_end: formData.scheduled_end || undefined,
      sending_hours_start: formData.sending_hours_enabled
        ? formData.sending_hours_start
        : "00:00",
      sending_hours_end: formData.sending_hours_enabled
        ? formData.sending_hours_end
        : "23:59",
      sending_days: formData.sending_days,
      timezone: formData.timezone,
      calls_per_minute: formData.calls_per_minute,
    };
    await onSubmit(request, selectedContactIds);
  };

  return (
    <BaseCampaignWizard
      steps={steps}
      initialFormData={initialFormData}
      onSubmit={handleSubmit}
      isSubmitting={isSubmitting}
      onCancel={onCancel}
    />
  );
}
