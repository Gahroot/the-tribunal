"use client";

import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  FileText,
  Users,
  MessageSquare,
  Bot,
  Clock,
  Eye,
  Send,
  Loader2,
  Phone,
  Tag,
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
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription } from "@/components/ui/alert";

import { ContactSelector } from "./contact-selector";
import { AgentSelector } from "./agent-selector";
import { OfferSelector } from "./offer-selector";

import type { Contact, Agent, Offer, PhoneNumber, SMSCampaign } from "@/types";
import type { CreateSMSCampaignRequest } from "@/lib/api/sms-campaigns";
import { DAYS_OF_WEEK, TIMEZONES } from "@/lib/constants";

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
  contacts: Contact[];
  agents: Agent[];
  offers: Offer[];
  phoneNumbers: PhoneNumber[];
  onSubmit: (
    data: CreateSMSCampaignRequest,
    contactIds: number[]
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
  contacts,
  agents,
  offers,
  phoneNumbers,
  onSubmit,
  onCreateOffer,
  onCancel,
  isSubmitting = false,
}: SMSCampaignWizardProps) {
  const [currentStep, setCurrentStep] = useState<StepId>("basics");
  const [formData, setFormData] = useState<CampaignFormData>(initialFormData);
  const [selectedContactIds, setSelectedContactIds] = useState<number[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const currentStepIndex = STEPS.findIndex((s) => s.id === currentStep);

  const updateFormData = useCallback(
    <K extends keyof CampaignFormData>(key: K, value: CampaignFormData[K]) => {
      setFormData((prev) => ({ ...prev, [key]: value }));
      // Clear error when field is updated
      if (errors[key]) {
        setErrors((prev) => {
          const next = { ...prev };
          delete next[key];
          return next;
        });
      }
    },
    [errors]
  );

  const validateStep = useCallback(
    (step: StepId): boolean => {
      const newErrors: Record<string, string> = {};

      switch (step) {
        case "basics":
          if (!formData.name.trim()) newErrors.name = "Campaign name is required";
          if (!formData.from_phone_number)
            newErrors.from_phone_number = "Phone number is required";
          break;
        case "contacts":
          if (selectedContactIds.length === 0)
            newErrors.contacts = "Select at least one contact";
          break;
        case "message":
          if (!formData.initial_message.trim())
            newErrors.initial_message = "Message is required";
          break;
        case "schedule":
          if (formData.sending_days.length === 0)
            newErrors.sending_days = "Select at least one day";
          break;
      }

      setErrors(newErrors);
      return Object.keys(newErrors).length === 0;
    },
    [formData, selectedContactIds]
  );

  const goToStep = (step: StepId) => {
    // Validate current step before moving forward
    const targetIndex = STEPS.findIndex((s) => s.id === step);
    if (targetIndex > currentStepIndex) {
      if (!validateStep(currentStep)) return;
    }
    setCurrentStep(step);
  };

  const goNext = () => {
    if (!validateStep(currentStep)) return;
    const nextIndex = currentStepIndex + 1;
    if (nextIndex < STEPS.length) {
      setCurrentStep(STEPS[nextIndex].id);
    }
  };

  const goPrevious = () => {
    const prevIndex = currentStepIndex - 1;
    if (prevIndex >= 0) {
      setCurrentStep(STEPS[prevIndex].id);
    }
  };

  const handleSubmit = async () => {
    // Final validation
    for (const step of STEPS) {
      if (!validateStep(step.id)) {
        setCurrentStep(step.id);
        return;
      }
    }

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
      // When sending hours are disabled, use 24-hour window (no restrictions)
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
    const textarea = document.getElementById(
      "initial-message"
    ) as HTMLTextAreaElement;
    if (textarea) {
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const newMessage =
        formData.initial_message.slice(0, start) +
        placeholder +
        formData.initial_message.slice(end);
      updateFormData("initial_message", newMessage);
      // Restore cursor position
      setTimeout(() => {
        textarea.focus();
        textarea.setSelectionRange(
          start + placeholder.length,
          start + placeholder.length
        );
      }, 0);
    } else {
      updateFormData(
        "initial_message",
        formData.initial_message + placeholder
      );
    }
  };

  const selectedOffer = offers.find((o) => o.id === formData.offer_id);
  const selectedAgent = agents.find((a) => a.id === formData.agent_id);
  const selectedPhone = phoneNumbers.find(
    (p) => p.phone_number === formData.from_phone_number
  );

  const renderStepContent = () => {
    switch (currentStep) {
      case "basics":
        return (
          <div className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="campaign-name">Campaign Name *</Label>
              <Input
                id="campaign-name"
                placeholder="e.g., Summer Sale Outreach"
                value={formData.name}
                onChange={(e) => updateFormData("name", e.target.value)}
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
                onChange={(e) => updateFormData("description", e.target.value)}
                rows={3}
              />
            </div>

            <div className="space-y-2">
              <Label>From Phone Number *</Label>
              <Select
                value={formData.from_phone_number}
                onValueChange={(v) => updateFormData("from_phone_number", v)}
              >
                <SelectTrigger
                  className={errors.from_phone_number ? "border-destructive" : ""}
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
                  No SMS-enabled phone numbers available
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
            <ContactSelector
              contacts={contacts}
              selectedIds={selectedContactIds}
              onSelectionChange={setSelectedContactIds}
            />
          </div>
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
                  updateFormData("initial_message", e.target.value)
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
                onSelect={(id) => updateFormData("offer_id", id)}
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
                  onCheckedChange={(v) => updateFormData("follow_up_enabled", v)}
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
                          updateFormData("follow_up_delay_hours", parseInt(v))
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
                          updateFormData("max_follow_ups", parseInt(v))
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
                        updateFormData("follow_up_message", e.target.value)
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
                onCheckedChange={(v) => updateFormData("ai_enabled", v)}
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
                  onSelect={(id) => updateFormData("agent_id", id)}
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
                      updateFormData("qualification_criteria", e.target.value)
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
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="scheduled-start">Start Date (Optional)</Label>
                <Input
                  id="scheduled-start"
                  type="datetime-local"
                  value={formData.scheduled_start || ""}
                  onChange={(e) =>
                    updateFormData("scheduled_start", e.target.value || undefined)
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
                    updateFormData("scheduled_end", e.target.value || undefined)
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
                    <h4 className="font-medium">Restrict Sending Hours</h4>
                    <p className="text-sm text-muted-foreground">
                      Only send messages during specific hours
                    </p>
                  </div>
                </div>
                <Switch
                  checked={formData.sending_hours_enabled}
                  onCheckedChange={(v) => updateFormData("sending_hours_enabled", v)}
                />
              </div>

              {formData.sending_hours_enabled && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="grid grid-cols-3 gap-4 pl-4 border-l-2 border-muted"
                >
                  <div className="space-y-2">
                    <Label>Start Time</Label>
                    <Input
                      type="time"
                      value={formData.sending_hours_start}
                      onChange={(e) =>
                        updateFormData("sending_hours_start", e.target.value)
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>End Time</Label>
                    <Input
                      type="time"
                      value={formData.sending_hours_end}
                      onChange={(e) =>
                        updateFormData("sending_hours_end", e.target.value)
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Timezone</Label>
                    <Select
                      value={formData.timezone}
                      onValueChange={(v) => updateFormData("timezone", v)}
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
                Sending Days
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
                          updateFormData(
                            "sending_days",
                            formData.sending_days.filter((d) => d !== day.value)
                          );
                        } else {
                          updateFormData("sending_days", [
                            ...formData.sending_days,
                            day.value,
                          ].sort());
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
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Messages per Minute</Label>
                  <Select
                    value={String(formData.messages_per_minute)}
                    onValueChange={(v) =>
                      updateFormData("messages_per_minute", parseInt(v))
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
                      updateFormData("max_messages_per_contact", parseInt(v))
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
                      {selectedPhone?.friendly_name || formData.from_phone_number}
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
                    {selectedContactIds.length}
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

            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Clock className="size-5" />
                  Schedule
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-muted-foreground">Sending hours:</span>
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
                      .map((d) => DAYS_OF_WEEK.find((day) => day.value === d)?.label)
                      .join(", ")}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-muted-foreground">Rate:</span>
                  <span>
                    {formData.messages_per_minute} messages/min,{" "}
                    {formData.max_messages_per_contact === 0
                      ? "unlimited messages per contact"
                      : `max ${formData.max_messages_per_contact} per contact`}
                  </span>
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
    <div className="flex flex-col h-full">
      {/* Step indicators */}
      <div className="flex items-center justify-between px-6 py-4 border-b bg-muted/30">
        {STEPS.map((step, index) => {
          const Icon = step.icon;
          const isCompleted = index < currentStepIndex;
          const isCurrent = step.id === currentStep;

          return (
            <button
              key={step.id}
              onClick={() => goToStep(step.id)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-colors ${
                isCurrent
                  ? "bg-primary text-primary-foreground"
                  : isCompleted
                  ? "text-primary hover:bg-primary/10"
                  : "text-muted-foreground hover:bg-muted"
              }`}
            >
              <div
                className={`size-8 rounded-full flex items-center justify-center ${
                  isCurrent
                    ? "bg-primary-foreground/20"
                    : isCompleted
                    ? "bg-primary/20"
                    : "bg-muted"
                }`}
              >
                {isCompleted ? (
                  <Check className="size-4" />
                ) : (
                  <Icon className="size-4" />
                )}
              </div>
              <span className="text-sm font-medium hidden lg:block">
                {step.label}
              </span>
            </button>
          );
        })}
      </div>

      {/* Step content */}
      <ScrollArea className="flex-1">
        <div className="p-6 max-w-4xl mx-auto">
          <AnimatePresence mode="wait">
            <motion.div
              key={currentStep}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2 }}
            >
              {renderStepContent()}
            </motion.div>
          </AnimatePresence>
        </div>
      </ScrollArea>

      {/* Footer navigation */}
      <div className="flex items-center justify-between px-6 py-4 border-t bg-background">
        <div>
          {onCancel && (
            <Button variant="ghost" onClick={onCancel}>
              Cancel
            </Button>
          )}
        </div>
        <div className="flex items-center gap-2">
          {currentStepIndex > 0 && (
            <Button variant="outline" onClick={goPrevious}>
              <ArrowLeft className="size-4 mr-2" />
              Previous
            </Button>
          )}
          {currentStepIndex < STEPS.length - 1 ? (
            <Button onClick={goNext}>
              Next
              <ArrowRight className="size-4 ml-2" />
            </Button>
          ) : (
            <Button onClick={handleSubmit} disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <Loader2 className="size-4 mr-2 animate-spin" />
                  Creating...
                </>
              ) : (
                <>
                  <Send className="size-4 mr-2" />
                  Create Campaign
                </>
              )}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
