"use client";

import { useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  FileText,
  Users,
  Phone,
  MessageSquare,
  Clock,
  Eye,
  Send,
  Calendar,
  AlertCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription } from "@/components/ui/alert";

import { VirtualContactSelector } from "./virtual-contact-selector";
import { AgentSelector } from "./agent-selector";
import { SMSFallbackStep, type SMSFallbackMode } from "./sms-fallback-step";

import { useWizard } from "@/hooks/useWizard";
import { WizardContainer } from "@/components/wizard";

import type { Agent, PhoneNumber, VoiceCampaign } from "@/types";
import type { CreateVoiceCampaignRequest } from "@/lib/api/voice-campaigns";
import { DAYS_OF_WEEK, TIMEZONES } from "@/lib/constants";

// Step definitions
const STEPS = [
  { id: "basics", label: "Basics", icon: FileText },
  { id: "contacts", label: "Contacts", icon: Users },
  { id: "voice", label: "Voice Agent", icon: Phone },
  { id: "fallback", label: "SMS Fallback", icon: MessageSquare },
  { id: "schedule", label: "Schedule", icon: Clock },
  { id: "review", label: "Review", icon: Eye },
] as const;

type StepId = (typeof STEPS)[number]["id"];

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

interface CampaignFormData {
  name: string;
  description: string;
  from_phone_number: string;
  // Voice settings
  voice_agent_id?: string;
  enable_machine_detection: boolean;
  max_call_duration_seconds: number;
  // SMS fallback
  sms_fallback_enabled: boolean;
  sms_fallback_mode: SMSFallbackMode;
  sms_fallback_template: string;
  sms_fallback_agent_id?: string;
  // AI for responses
  ai_enabled: boolean;
  qualification_criteria: string;
  // Scheduling
  scheduled_start?: string;
  scheduled_end?: string;
  sending_hours_enabled: boolean;
  sending_hours_start: string;
  sending_hours_end: string;
  sending_days: number[];
  timezone: string;
  calls_per_minute: number;
}

const initialFormData: CampaignFormData = {
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
  sending_days: [1, 2, 3, 4, 5], // Mon-Fri
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
  const [selectedContactIds, setSelectedContactIds] = useState<Set<number>>(new Set());

  const validateStep = useCallback(
    (step: StepId, data: CampaignFormData, setErrors: React.Dispatch<React.SetStateAction<Record<string, string>>>) => {
      const newErrors: Record<string, string> = {};

      switch (step) {
        case "basics":
          if (!data.name.trim()) newErrors.name = "Campaign name is required";
          if (!data.from_phone_number)
            newErrors.from_phone_number = "Phone number is required";
          break;
        case "contacts":
          if (selectedContactIds.size === 0)
            newErrors.contacts = "Select at least one contact";
          break;
        case "voice":
          if (!data.voice_agent_id)
            newErrors.voice_agent_id = "Voice agent is required";
          break;
        case "fallback":
          if (data.sms_fallback_enabled) {
            if (
              data.sms_fallback_mode === "template" &&
              !data.sms_fallback_template.trim()
            ) {
              newErrors.template = "Fallback template is required";
            }
            if (
              data.sms_fallback_mode === "ai" &&
              !data.sms_fallback_agent_id
            ) {
              newErrors.agentId = "Select an agent for AI-generated messages";
            }
          }
          break;
        case "schedule":
          if (data.sending_days.length === 0)
            newErrors.sending_days = "Select at least one day";
          break;
      }

      setErrors(newErrors);
      return Object.keys(newErrors).length === 0;
    },
    [selectedContactIds]
  );

  const wizard = useWizard<StepId, CampaignFormData>({
    steps: STEPS,
    initialFormData,
    validateStep,
  });

  const { formData, errors, updateField } = wizard;

  const handleSubmit = async () => {
    if (!wizard.validateAllSteps()) return;

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

  const selectedVoiceAgent = voiceAgents.find(
    (a) => a.id === formData.voice_agent_id
  );
  const selectedFallbackAgent = textAgents.find(
    (a) => a.id === formData.sms_fallback_agent_id
  );
  const selectedPhone = phoneNumbers.find(
    (p) => p.phone_number === formData.from_phone_number
  );

  const renderStepContent = () => {
    switch (wizard.currentStepId) {
      case "basics":
        return (
          <div className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="campaign-name">Campaign Name *</Label>
              <Input
                id="campaign-name"
                placeholder="e.g., Follow-up Calls - January"
                value={formData.name}
                onChange={(e) => updateField("name", e.target.value)}
                className={errors.name ? "border-destructive" : ""}
              />
              {errors.name && (
                <p className="text-sm text-destructive">{errors.name}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="campaign-description">Description</Label>
              <Textarea
                id="campaign-description"
                placeholder="Brief description of this campaign..."
                value={formData.description}
                onChange={(e) => updateField("description", e.target.value)}
                rows={3}
              />
            </div>

            <div className="space-y-2">
              <Label>From Phone Number *</Label>
              <Select
                value={formData.from_phone_number}
                onValueChange={(v) => updateField("from_phone_number", v)}
              >
                <SelectTrigger
                  className={
                    errors.from_phone_number ? "border-destructive" : ""
                  }
                >
                  <SelectValue placeholder="Select a phone number" />
                </SelectTrigger>
                <SelectContent>
                  {phoneNumbers.map((phone) => (
                    <SelectItem key={phone.id} value={phone.phone_number}>
                      <div className="flex items-center gap-2">
                        <Phone className="size-4" />
                        <span>{phone.phone_number}</span>
                        {phone.friendly_name && (
                          <span className="text-muted-foreground">
                            ({phone.friendly_name})
                          </span>
                        )}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {errors.from_phone_number && (
                <p className="text-sm text-destructive">
                  {errors.from_phone_number}
                </p>
              )}
              {phoneNumbers.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  No voice-enabled phone numbers available
                </p>
              )}
            </div>
          </div>
        );

      case "contacts":
        return (
          <div className="space-y-4">
            {errors.contacts && (
              <Alert variant="destructive">
                <AlertCircle className="size-4" />
                <AlertDescription>{errors.contacts}</AlertDescription>
              </Alert>
            )}
            <VirtualContactSelector
              workspaceId={workspaceId}
              selectedIds={selectedContactIds}
              onSelectionChange={setSelectedContactIds}
            />
          </div>
        );

      case "voice":
        return (
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
        );

      case "fallback":
        return (
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
        );

      case "schedule":
        return (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="scheduled-start">Start Date (Optional)</Label>
                <Input
                  id="scheduled-start"
                  type="datetime-local"
                  value={formData.scheduled_start || ""}
                  onChange={(e) =>
                    updateField(
                      "scheduled_start",
                      e.target.value || undefined
                    )
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="scheduled-end">End Date (Optional)</Label>
                <Input
                  id="scheduled-end"
                  type="datetime-local"
                  value={formData.scheduled_end || ""}
                  onChange={(e) =>
                    updateField("scheduled_end", e.target.value || undefined)
                  }
                />
              </div>
            </div>

            <Separator />

            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
                <div className="flex items-center gap-2">
                  <Clock className="size-4" />
                  <div>
                    <h4 className="font-medium">Restrict Calling Hours</h4>
                    <p className="text-sm text-muted-foreground">
                      Only make calls during specific hours
                    </p>
                  </div>
                </div>
                <Switch
                  checked={formData.sending_hours_enabled}
                  onCheckedChange={(v) =>
                    updateField("sending_hours_enabled", v)
                  }
                />
              </div>

              {formData.sending_hours_enabled && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  className="grid grid-cols-3 gap-4 pl-4 border-l-2 border-muted"
                >
                  <div className="space-y-2">
                    <Label>Start Time</Label>
                    <Input
                      type="time"
                      value={formData.sending_hours_start}
                      onChange={(e) =>
                        updateField("sending_hours_start", e.target.value)
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>End Time</Label>
                    <Input
                      type="time"
                      value={formData.sending_hours_end}
                      onChange={(e) =>
                        updateField("sending_hours_end", e.target.value)
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Timezone</Label>
                    <Select
                      value={formData.timezone}
                      onValueChange={(v) => updateField("timezone", v)}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {TIMEZONES.map((tz) => (
                          <SelectItem key={tz} value={tz}>
                            {tz.replace("_", " ").replace("America/", "")}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </motion.div>
              )}
            </div>

            <div className="space-y-4">
              <h4 className="font-medium flex items-center gap-2">
                <Calendar className="size-4" />
                Calling Days
              </h4>
              <div className="flex gap-2">
                {DAYS_OF_WEEK.map((day) => {
                  const isSelected = formData.sending_days.includes(day.value);
                  return (
                    <Button
                      key={day.value}
                      variant={isSelected ? "default" : "outline"}
                      size="sm"
                      className="w-12"
                      onClick={() => {
                        if (isSelected) {
                          updateField(
                            "sending_days",
                            formData.sending_days.filter((d) => d !== day.value)
                          );
                        } else {
                          updateField(
                            "sending_days",
                            [...formData.sending_days, day.value].sort()
                          );
                        }
                      }}
                    >
                      {day.label}
                    </Button>
                  );
                })}
              </div>
              {errors.sending_days && (
                <p className="text-sm text-destructive">{errors.sending_days}</p>
              )}
            </div>

            <Separator />

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
                  Lower rates are recommended to avoid overwhelming your agents
                </p>
              </div>
            </div>
          </div>
        );

      case "review":
        return (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Campaign Summary</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-sm text-muted-foreground">Name</p>
                    <p className="font-medium">{formData.name}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">From</p>
                    <p className="font-medium">
                      {selectedPhone?.friendly_name ||
                        formData.from_phone_number}
                    </p>
                  </div>
                </div>
                {formData.description && (
                  <div>
                    <p className="text-sm text-muted-foreground">Description</p>
                    <p className="font-medium">{formData.description}</p>
                  </div>
                )}
              </CardContent>
            </Card>

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
                  {formData.enable_machine_detection ? "Enabled" : "Disabled"}
                </div>
                <div className="text-sm text-muted-foreground">
                  Max call duration: {formData.max_call_duration_seconds / 60}{" "}
                  minute(s)
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
                      className="bg-green-500/10 text-green-600"
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

            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Clock className="size-5" />
                  Schedule
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-muted-foreground">Calling hours:</span>
                  <span>
                    {formData.sending_hours_enabled
                      ? `${formData.sending_hours_start} - ${formData.sending_hours_end} (${formData.timezone.replace("America/", "")})`
                      : "Anytime (no restrictions)"}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-muted-foreground">Days:</span>
                  <span>
                    {formData.sending_days
                      .map(
                        (d) => DAYS_OF_WEEK.find((day) => day.value === d)?.label
                      )
                      .join(", ")}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-muted-foreground">Rate:</span>
                  <span>{formData.calls_per_minute} calls/min</span>
                </div>
              </CardContent>
            </Card>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <WizardContainer
      steps={STEPS}
      currentStepId={wizard.currentStepId}
      currentStepIndex={wizard.currentStepIndex}
      onStepClick={wizard.goToStep}
      isFirstStep={wizard.isFirstStep}
      isLastStep={wizard.isLastStep}
      onPrevious={wizard.goPrevious}
      onNext={wizard.goNext}
      onSubmit={handleSubmit}
      isSubmitting={isSubmitting}
      onCancel={onCancel}
      submitLabel="Create Campaign"
      submitIcon={Send}
    >
      {renderStepContent()}
    </WizardContainer>
  );
}
