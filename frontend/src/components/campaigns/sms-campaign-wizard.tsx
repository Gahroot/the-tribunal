"use client";

import { useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  FileText,
  Users,
  MessageSquare,
  Bot,
  Clock,
  Eye,
  Send,
  Tag,
} from "lucide-react";

import { Button } from "@/components/ui/button";
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

import { AgentSelector } from "./agent-selector";
import { OfferSelector } from "./offer-selector";
import {
  BasicsStep,
  ContactsStep,
  ScheduleStep,
  ReviewSummaryCard,
  ReviewScheduleCard,
} from "./steps";

import { useWizard } from "@/hooks/useWizard";
import { WizardContainer } from "@/components/wizard";
import { insertPlaceholderAtCursor } from "@/lib/utils/placeholder";

import type { Agent, Offer, PhoneNumber, SMSCampaign } from "@/types";
import type { CreateSMSCampaignRequest } from "@/lib/api/sms-campaigns";

// Step definitions
const STEPS = [
  { id: "basics", label: "Basics", icon: FileText },
  { id: "contacts", label: "Contacts", icon: Users },
  { id: "message", label: "Message", icon: MessageSquare },
  { id: "agent", label: "AI Agent", icon: Bot },
  { id: "schedule", label: "Schedule", icon: Clock },
  { id: "review", label: "Review", icon: Eye },
] as const;

type StepId = (typeof STEPS)[number]["id"];

interface SMSCampaignWizardProps {
  workspaceId: string;
  agents: Agent[];
  offers: Offer[];
  phoneNumbers: PhoneNumber[];
  onSubmit: (
    data: CreateSMSCampaignRequest,
    contactIds: Set<number>
  ) => Promise<SMSCampaign>;
  onCreateOffer?: (offer: Partial<Offer>) => Promise<void>;
  onCancel?: () => void;
  isSubmitting?: boolean;
}

interface CampaignFormData {
  name: string;
  description: string;
  from_phone_number: string;
  initial_message: string;
  agent_id?: string;
  offer_id?: string;
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
  // Rate limiting
  messages_per_minute: number;
  max_messages_per_contact: number;
  // Follow-ups
  follow_up_enabled: boolean;
  follow_up_delay_hours: number;
  follow_up_message: string;
  max_follow_ups: number;
}

const initialFormData: CampaignFormData = {
  name: "",
  description: "",
  from_phone_number: "",
  initial_message: "",
  agent_id: undefined,
  offer_id: undefined,
  ai_enabled: true,
  qualification_criteria: "",
  sending_hours_enabled: false,
  sending_hours_start: "09:00",
  sending_hours_end: "17:00",
  sending_days: [1, 2, 3, 4, 5], // Mon-Fri
  timezone: "America/New_York",
  messages_per_minute: 10,
  max_messages_per_contact: 3,
  follow_up_enabled: false,
  follow_up_delay_hours: 24,
  follow_up_message: "",
  max_follow_ups: 2,
};

export function SMSCampaignWizard({
  workspaceId,
  agents,
  offers,
  phoneNumbers,
  onSubmit,
  onCreateOffer,
  onCancel,
  isSubmitting = false,
}: SMSCampaignWizardProps) {
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
        case "message":
          if (!data.initial_message.trim())
            newErrors.initial_message = "Message is required";
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

    const request: CreateSMSCampaignRequest = {
      name: formData.name,
      description: formData.description || undefined,
      from_phone_number: formData.from_phone_number,
      initial_message: formData.initial_message,
      agent_id: formData.agent_id,
      offer_id: formData.offer_id,
      ai_enabled: formData.ai_enabled,
      qualification_criteria: formData.qualification_criteria || undefined,
      scheduled_start: formData.scheduled_start || undefined,
      scheduled_end: formData.scheduled_end || undefined,
      sending_hours_start: formData.sending_hours_enabled ? formData.sending_hours_start : "00:00",
      sending_hours_end: formData.sending_hours_enabled ? formData.sending_hours_end : "23:59",
      sending_days: formData.sending_days,
      timezone: formData.timezone,
      messages_per_minute: formData.messages_per_minute,
      max_messages_per_contact: formData.max_messages_per_contact,
      follow_up_enabled: formData.follow_up_enabled,
      follow_up_delay_hours: formData.follow_up_delay_hours,
      follow_up_message: formData.follow_up_message || undefined,
      max_follow_ups: formData.max_follow_ups,
    };

    await onSubmit(request, selectedContactIds);
  };

  const insertPlaceholder = (placeholder: string) => {
    insertPlaceholderAtCursor(
      "initial-message",
      placeholder,
      formData.initial_message,
      (v) => updateField("initial_message", v)
    );
  };

  const selectedOffer = offers.find((o) => o.id === formData.offer_id);
  const selectedAgent = agents.find((a) => a.id === formData.agent_id);
  const selectedPhone = phoneNumbers.find(
    (p) => p.phone_number === formData.from_phone_number
  );

  const smsRateLimitingSlot = (
    <div className="space-y-4">
      <h4 className="font-medium">Rate Limiting</h4>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label>Messages per Minute</Label>
          <Select
            value={String(formData.messages_per_minute)}
            onValueChange={(v) =>
              updateField("messages_per_minute", parseInt(v))
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="5">5 / minute</SelectItem>
              <SelectItem value="10">10 / minute</SelectItem>
              <SelectItem value="20">20 / minute</SelectItem>
              <SelectItem value="30">30 / minute</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label>Max Messages per Contact</Label>
          <Select
            value={String(formData.max_messages_per_contact)}
            onValueChange={(v) =>
              updateField("max_messages_per_contact", parseInt(v))
            }
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="1">1 message</SelectItem>
              <SelectItem value="2">2 messages</SelectItem>
              <SelectItem value="3">3 messages</SelectItem>
              <SelectItem value="5">5 messages</SelectItem>
              <SelectItem value="10">10 messages</SelectItem>
              <SelectItem value="0">Unlimited</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
    </div>
  );

  const renderStepContent = () => {
    switch (wizard.currentStepId) {
      case "basics":
        return (
          <BasicsStep
            name={formData.name}
            description={formData.description}
            fromPhoneNumber={formData.from_phone_number}
            phoneNumbers={phoneNumbers}
            errors={errors}
            onNameChange={(v) => updateField("name", v)}
            onDescriptionChange={(v) => updateField("description", v)}
            onPhoneChange={(v) => updateField("from_phone_number", v)}
            namePlaceholder="e.g., Summer Sale Outreach"
            emptyPhoneLabel="No SMS-enabled phone numbers available"
          />
        );

      case "contacts":
        return (
          <ContactsStep
            workspaceId={workspaceId}
            selectedIds={selectedContactIds}
            onSelectionChange={setSelectedContactIds}
            error={errors.contacts}
          />
        );

      case "message":
        return (
          <div className="space-y-6">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="initial-message">Initial Message *</Label>
                <div className="flex items-center gap-1">
                  <span className="text-xs text-muted-foreground mr-2">
                    Insert:
                  </span>
                  {[
                    { label: "First Name", value: "{first_name}" },
                    { label: "Last Name", value: "{last_name}" },
                    { label: "Company", value: "{company_name}" },
                  ].map((p) => (
                    <Button
                      key={p.value}
                      variant="outline"
                      size="sm"
                      className="text-xs h-7"
                      onClick={() => insertPlaceholder(p.value)}
                    >
                      {p.label}
                    </Button>
                  ))}
                </div>
              </div>
              <Textarea
                id="initial-message"
                placeholder="Hi {first_name}, we have an amazing offer for you..."
                value={formData.initial_message}
                onChange={(e) =>
                  updateField("initial_message", e.target.value)
                }
                rows={4}
                className={errors.initial_message ? "border-destructive" : ""}
              />
              {errors.initial_message && (
                <p className="text-sm text-destructive">
                  {errors.initial_message}
                </p>
              )}
              <p className="text-xs text-muted-foreground">
                {formData.initial_message.length}/160 characters (standard SMS)
              </p>
            </div>

            <Separator />

            <div className="space-y-4">
              <h4 className="font-medium flex items-center gap-2">
                <Tag className="size-4" />
                Attach an Offer (Optional)
              </h4>
              <OfferSelector
                offers={offers}
                selectedId={formData.offer_id}
                onSelect={(id) => updateField("offer_id", id)}
                onCreateOffer={onCreateOffer}
              />
            </div>

            <Separator />

            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-medium">Follow-up Messages</h4>
                  <p className="text-sm text-muted-foreground">
                    Automatically send follow-ups if no response
                  </p>
                </div>
                <Switch
                  checked={formData.follow_up_enabled}
                  onCheckedChange={(v) => updateField("follow_up_enabled", v)}
                />
              </div>

              {formData.follow_up_enabled && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="space-y-4 pl-4 border-l-2 border-muted"
                >
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>Delay Before Follow-up</Label>
                      <Select
                        value={String(formData.follow_up_delay_hours)}
                        onValueChange={(v) =>
                          updateField("follow_up_delay_hours", parseInt(v))
                        }
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="12">12 hours</SelectItem>
                          <SelectItem value="24">24 hours</SelectItem>
                          <SelectItem value="48">48 hours</SelectItem>
                          <SelectItem value="72">72 hours</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label>Max Follow-ups</Label>
                      <Select
                        value={String(formData.max_follow_ups)}
                        onValueChange={(v) =>
                          updateField("max_follow_ups", parseInt(v))
                        }
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="1">1</SelectItem>
                          <SelectItem value="2">2</SelectItem>
                          <SelectItem value="3">3</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="follow-up-message">Follow-up Message</Label>
                    <Textarea
                      id="follow-up-message"
                      placeholder="Just following up on my previous message..."
                      value={formData.follow_up_message}
                      onChange={(e) =>
                        updateField("follow_up_message", e.target.value)
                      }
                      rows={3}
                    />
                  </div>
                </motion.div>
              )}
            </div>
          </div>
        );

      case "agent":
        return (
          <div className="space-y-6">
            <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
              <div>
                <h4 className="font-medium">Enable AI Responses</h4>
                <p className="text-sm text-muted-foreground">
                  Let AI handle conversations automatically
                </p>
              </div>
              <Switch
                checked={formData.ai_enabled}
                onCheckedChange={(v) => updateField("ai_enabled", v)}
              />
            </div>

            {formData.ai_enabled && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="space-y-6"
              >
                <AgentSelector
                  agents={agents}
                  selectedId={formData.agent_id}
                  onSelect={(id) => updateField("agent_id", id)}
                  showTextAgentsOnly={true}
                />

                <div className="space-y-2">
                  <Label htmlFor="qualification-criteria">
                    Qualification Criteria (Optional)
                  </Label>
                  <Textarea
                    id="qualification-criteria"
                    placeholder="e.g., Interested in scheduling a demo, Has budget over $1000..."
                    value={formData.qualification_criteria}
                    onChange={(e) =>
                      updateField("qualification_criteria", e.target.value)
                    }
                    rows={3}
                  />
                  <p className="text-xs text-muted-foreground">
                    The AI will mark contacts as qualified when they meet these
                    criteria
                  </p>
                </div>
              </motion.div>
            )}
          </div>
        );

      case "schedule":
        return (
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
            onSendingHoursEnabledChange={(v) => updateField("sending_hours_enabled", v)}
            onSendingHoursStartChange={(v) => updateField("sending_hours_start", v)}
            onSendingHoursEndChange={(v) => updateField("sending_hours_end", v)}
            onSendingDaysChange={(v) => updateField("sending_days", v)}
            onTimezoneChange={(v) => updateField("timezone", v)}
            sendingHoursLabel="Restrict Sending Hours"
            sendingHoursDescription="Only send messages during specific hours"
            daysLabel="Sending Days"
            rateLimitingSlot={smsRateLimitingSlot}
          />
        );

      case "review":
        return (
          <div className="space-y-6">
            <ReviewSummaryCard
              name={formData.name}
              description={formData.description || undefined}
              fromPhoneDisplay={selectedPhone?.friendly_name || formData.from_phone_number}
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
                  <span className="text-muted-foreground">contacts selected</span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <MessageSquare className="size-5" />
                  Message
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="p-4 bg-muted rounded-lg">
                  <p className="whitespace-pre-wrap">{formData.initial_message}</p>
                </div>
                {selectedOffer && (
                  <div className="flex items-center gap-2">
                    <Tag className="size-4 text-green-600" />
                    <span className="text-sm">Attached offer:</span>
                    <Badge variant="secondary" className="bg-green-500/10 text-green-600">
                      {selectedOffer.name}
                    </Badge>
                  </div>
                )}
                {formData.follow_up_enabled && (
                  <div className="text-sm text-muted-foreground">
                    Follow-up enabled: {formData.max_follow_ups} message(s) after{" "}
                    {formData.follow_up_delay_hours} hours
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Bot className="size-5" />
                  AI Configuration
                </CardTitle>
              </CardHeader>
              <CardContent>
                {formData.ai_enabled ? (
                  <div className="space-y-2">
                    {selectedAgent ? (
                      <div className="flex items-center gap-2">
                        <Badge variant="default">{selectedAgent.name}</Badge>
                        <span className="text-sm text-muted-foreground">
                          will handle responses
                        </span>
                      </div>
                    ) : (
                      <p className="text-muted-foreground">
                        AI enabled but no agent selected
                      </p>
                    )}
                    {formData.qualification_criteria && (
                      <div className="mt-2">
                        <p className="text-sm text-muted-foreground">
                          Qualification criteria:
                        </p>
                        <p className="text-sm">{formData.qualification_criteria}</p>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-muted-foreground">
                    AI responses disabled - manual responses only
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
              hoursLabel="Sending hours"
              rateDescription={
                <>
                  {formData.messages_per_minute} messages/min,{" "}
                  {formData.max_messages_per_contact === 0
                    ? "unlimited messages per contact"
                    : `max ${formData.max_messages_per_contact} per contact`}
                </>
              }
            />
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
