"use client";

import { Eye, PenLine, Send } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { toast } from "sonner";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { assistantApi } from "@/lib/api/assistant";
import type { CreateSMSCampaignRequest } from "@/lib/api/sms-campaigns";
import { DAYS_OF_WEEK, TIMEZONE_OPTIONS } from "@/lib/constants";
import { messages } from "@/lib/messages";
import { formatDateTime } from "@/lib/utils/date";
import { getApiErrorMessage } from "@/lib/utils/errors";
import type { Agent, Offer, PhoneNumber, SMSCampaign } from "@/types";

import {
  type BasicsFields,
  type ScheduleFields,
  initialBasicsFields,
  initialScheduleFields,
  makeBasicsStep,
  makeContactsStep,
  makeScheduleStep,
  mapScheduleToRequest,
  validateAgent,
  validateBasics,
} from "./_shared";
import { BaseCampaignWizard } from "./base-campaign-wizard";
import { SendConfirmationDialog } from "./send-confirmation-dialog";
import {
  type AgentStepFields,
  type CampaignMedia,
  type MessageStepFields,
  makeAgentStep,
  makeMessageStep,
  PhonePreview,
} from "./sms-steps";
import type { WizardStep, WizardStepRenderArgs } from "./wizard-types";

type StepId = "compose" | "audience" | "preview";

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

interface SMSFormData
  extends BasicsFields,
    ScheduleFields,
    MessageStepFields,
    AgentStepFields {
  messages_per_minute: number;
  max_messages_per_contact: number;
}

interface PendingSend {
  request: CreateSMSCampaignRequest;
  contactIds: number[];
  campaignName: string;
  senderLabel: string;
  recipients: number;
  scheduleSummary: string;
  paceSummary: string;
  message: string;
}

const initialFormData: SMSFormData = {
  ...initialBasicsFields,
  ...initialScheduleFields,
  initial_message: "",
  agent_id: undefined,
  offer_id: undefined,
  ai_enabled: true,
  qualification_criteria: "",
  messages_per_minute: 10,
  max_messages_per_contact: 3,
  follow_up_enabled: false,
  follow_up_delay_hours: 24,
  follow_up_message: "",
  max_follow_ups: 2,
};

function mergeValidation(
  ...results: Array<
    Readonly<Record<string, string | undefined>> | null | undefined
  >
): Record<string, string> {
  const merged: Record<string, string> = {};
  for (const result of results) {
    if (!result) continue;
    for (const [key, value] of Object.entries(result)) {
      if (typeof value === "string" && value.length > 0) merged[key] = value;
    }
  }
  return merged;
}

function senderDisplayName(
  phone: PhoneNumber | undefined,
  fallback: string
): string {
  if (!phone) return fallback;
  const address = phone.mac_relay_sender_id || phone.phone_number;
  const label = phone.friendly_name || address;
  return phone.imessage_enabled ? `${label} · iMessage` : label;
}

function formatHour(value: string): string {
  const [hourRaw, minuteRaw] = value.split(":");
  const hour = Number(hourRaw);
  if (Number.isNaN(hour)) return value;
  const minute = Number.isNaN(Number(minuteRaw)) ? 0 : Number(minuteRaw);
  const period = hour >= 12 ? "PM" : "AM";
  const hour12 = hour % 12 || 12;
  return `${hour12}:${String(minute).padStart(2, "0")} ${period}`;
}

function timezoneLabel(value: string): string {
  const option = TIMEZONE_OPTIONS.find((tz) => tz.value === value);
  if (option) return option.label;
  const city = value.split("/").pop() ?? value;
  return city.replace(/_/g, " ");
}

function sanitizeAiDraft(raw: string): string {
  let text = raw.trim();
  text = text.replace(/^```[a-z]*\n?/i, "").replace(/\n?```$/, "").trim();
  text = text.replace(/^(?:message|sms|draft)\s*:\s*/i, "");
  if (
    (text.startsWith("\"") && text.endsWith("\"")) ||
    (text.startsWith("\u201c") && text.endsWith("\u201d"))
  ) {
    text = text.slice(1, -1).trim();
  }
  return text.trim();
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-border/60 py-2 last:border-0 last:pb-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-right text-sm font-medium">{value}</span>
    </div>
  );
}

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
  const [selectedContactIds, setSelectedContactIds] = useState<Set<number>>(
    new Set()
  );
  const [media, setMedia] = useState<CampaignMedia | null>(null);
  const [isGeneratingDraft, setIsGeneratingDraft] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingSend, setPendingSend] = useState<PendingSend | null>(null);
  // Reused across generate clicks so retries stay in one assistant thread.
  const [aiConversationId, setAiConversationId] = useState<string | null>(null);

  // AI "generate" half of the composer's generate → insert → edit loop. The
  // returned draft is inserted into the textarea by the message step, where
  // the operator can edit it before sending.
  const generateDraft = useCallback(
    async (ctx: {
      name: string;
      description: string;
      currentMessage: string;
      offerName?: string;
    }): Promise<string | null> => {
      setIsGeneratingDraft(true);
      try {
        const prompt = [
          "You write concise SMS outreach messages for a sales campaign.",
          `Campaign: ${ctx.name || "Untitled campaign"}.`,
          ctx.description ? `Context: ${ctx.description}.` : "",
          ctx.offerName ? `Offer: ${ctx.offerName}.` : "",
          ctx.currentMessage
            ? `The operator started writing: "${ctx.currentMessage}" — continue or improve it.`
            : "",
          "Reply with only the message text: at most 300 characters, no",
          "quotes or labels, use {first_name} for personalization, friendly",
          "and direct tone, no emoji.",
        ]
          .filter(Boolean)
          .join(" ");
        const response = await assistantApi.chat(
          workspaceId,
          prompt,
          aiConversationId
        );
        if (response.conversation_id) {
          setAiConversationId(response.conversation_id);
        }
        const draft = sanitizeAiDraft(response.response ?? "");
        if (!draft) {
          toast.error(messages.campaigns.aiDraftFailed);
          return null;
        }
        return draft;
      } catch (error) {
        toast.error(getApiErrorMessage(error, messages.campaigns.aiDraftFailed));
        return null;
      } finally {
        setIsGeneratingDraft(false);
      }
    },
    [workspaceId, aiConversationId]
  );

  const steps = useMemo<ReadonlyArray<WizardStep<StepId, SMSFormData>>>(() => {
    const basicsStep = makeBasicsStep<StepId, SMSFormData>({
      id: "compose",
      phoneNumbers,
      namePlaceholder: "e.g., Summer Sale Outreach",
      emptyPhoneLabel: "No SMS or iMessage sender identities available",
    });
    const messageStep = makeMessageStep<StepId, SMSFormData>({
      id: "compose",
      offers,
      onCreateOffer,
      generateDraft,
      isGeneratingDraft,
      media,
      onMediaChange: setMedia,
    });
    const agentStep = makeAgentStep<StepId, SMSFormData>({
      id: "compose",
      agents,
    });
    const contactsStep = makeContactsStep<StepId, SMSFormData>({
      id: "audience",
      workspaceId,
      selectedContactIds,
      setSelectedContactIds,
    });
    const scheduleStep = makeScheduleStep<StepId, SMSFormData>({
      id: "preview",
      sendingHoursLabel: "Restrict Sending Hours",
      sendingHoursDescription: "Only send messages during specific hours",
      daysLabel: "Sending Days",
      renderRateLimiting: ({ formData, updateField }) => (
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
      ),
    });

    const composeStep: WizardStep<StepId, SMSFormData> = {
      id: "compose",
      label: "Compose",
      icon: PenLine,
      validate: (data) =>
        mergeValidation(
          validateBasics(data),
          messageStep.validate?.(data),
          validateAgent(data)
        ),
      render: (args: WizardStepRenderArgs<SMSFormData>) => {
        const composePhone = phoneNumbers.find(
          (p) => p.phone_number === args.formData.from_phone_number
        );
        const composeOffer = offers.find(
          (o) => o.id === args.formData.offer_id
        );
        return (
          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Campaign details</CardTitle>
              </CardHeader>
              <CardContent>{basicsStep.render(args)}</CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Message</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_260px]">
                  <div>{messageStep.render(args)}</div>
                  <div className="min-w-0">
                    <PhonePreview
                      senderLabel={senderDisplayName(
                        composePhone,
                        args.formData.from_phone_number
                      )}
                      message={args.formData.initial_message}
                      media={media}
                      offer={composeOffer}
                      followUpEnabled={args.formData.follow_up_enabled}
                      followUpDelayHours={args.formData.follow_up_delay_hours}
                      followUpMessage={args.formData.follow_up_message}
                    />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg">AI replies</CardTitle>
              </CardHeader>
              <CardContent>{agentStep.render(args)}</CardContent>
            </Card>
          </div>
        );
      },
    };

    const audienceStep: WizardStep<StepId, SMSFormData> = {
      ...contactsStep,
      label: "Audience",
    };

    const previewStep: WizardStep<StepId, SMSFormData> = {
      id: "preview",
      label: "Preview",
      icon: Eye,
      validate: (data) => scheduleStep.validate?.(data) ?? null,
      render: ({ formData, errors, updateField }: WizardStepRenderArgs<SMSFormData>) => {
        const args = { formData, errors, updateField };
        const selectedPhone = phoneNumbers.find(
          (p) => p.phone_number === formData.from_phone_number
        );
        const selectedOffer = offers.find((o) => o.id === formData.offer_id);
        const selectedAgent = agents.find((a) => a.id === formData.agent_id);

        return (
          <div className="grid items-start gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
            <div className="mx-auto w-full max-w-[320px] lg:sticky lg:top-4">
              <PhonePreview
                senderLabel={senderDisplayName(
                  selectedPhone,
                  formData.from_phone_number
                )}
                message={formData.initial_message}
                media={media}
                offer={selectedOffer}
                followUpEnabled={formData.follow_up_enabled}
                followUpDelayHours={formData.follow_up_delay_hours}
                followUpMessage={formData.follow_up_message}
              />
            </div>

            <div className="space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Campaign summary</CardTitle>
                </CardHeader>
                <CardContent>
                  <div>
                    <SummaryRow
                      label="Campaign"
                      value={formData.name || "Untitled campaign"}
                    />
                    <SummaryRow
                      label="From"
                      value={senderDisplayName(
                        selectedPhone,
                        formData.from_phone_number
                      )}
                    />
                    <SummaryRow
                      label="Audience"
                      value={`${selectedContactIds.size} contact${selectedContactIds.size === 1 ? "" : "s"}`}
                    />
                    <SummaryRow
                      label="Offer"
                      value={selectedOffer?.name ?? "None"}
                    />
                    <SummaryRow
                      label="AI replies"
                      value={
                        formData.ai_enabled
                          ? (selectedAgent?.name ?? "Agent not selected")
                          : "Off (manual replies)"
                      }
                    />
                    <SummaryRow
                      label="Follow-ups"
                      value={
                        formData.follow_up_enabled
                          ? `${formData.max_follow_ups} after ${formData.follow_up_delay_hours}h`
                          : "Off"
                      }
                    />
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Schedule and pace</CardTitle>
                </CardHeader>
                <CardContent>{scheduleStep.render(args)}</CardContent>
              </Card>
            </div>
          </div>
        );
      },
    };

    return [composeStep, audienceStep, previewStep];
  }, [
    workspaceId,
    agents,
    offers,
    phoneNumbers,
    onCreateOffer,
    selectedContactIds,
    media,
    isGeneratingDraft,
    generateDraft,
  ]);

  // Runs only after validateAllSteps() passes in BaseCampaignWizard, so
  // invalid data never reaches the confirmation modal — each error surfaces
  // on its own step and the wizard jumps back to it.
  const handleWizardSubmit = (formData: SMSFormData) => {
    const request: CreateSMSCampaignRequest = {
      name: formData.name,
      description: formData.description || undefined,
      from_phone_number: formData.from_phone_number,
      initial_message: formData.initial_message,
      agent_id: formData.agent_id,
      offer_id: formData.offer_id,
      ai_enabled: formData.ai_enabled,
      qualification_criteria: formData.qualification_criteria || undefined,
      ...mapScheduleToRequest(formData),
      messages_per_minute: formData.messages_per_minute,
      max_messages_per_contact: formData.max_messages_per_contact,
      follow_up_enabled: formData.follow_up_enabled,
      follow_up_delay_hours: formData.follow_up_delay_hours,
      follow_up_message: formData.follow_up_message || undefined,
      max_follow_ups: formData.max_follow_ups,
    };

    const selectedPhone = phoneNumbers.find(
      (p) => p.phone_number === formData.from_phone_number
    );
    const days = formData.sending_days
      .map((d) => DAYS_OF_WEEK.find((day) => day.value === d)?.label)
      .filter(Boolean)
      .join(", ");
    const hours = formData.sending_hours_enabled
      ? `${formatHour(formData.sending_hours_start)} – ${formatHour(formData.sending_hours_end)}`
      : "Any hour";
    const scheduleParts = [
      hours,
      days || "No sending days",
      timezoneLabel(formData.timezone),
    ];
    if (formData.scheduled_start) {
      scheduleParts.push(`Starts ${formatDateTime(formData.scheduled_start)}`);
    }

    setPendingSend({
      request,
      contactIds: Array.from(selectedContactIds),
      campaignName: formData.name,
      senderLabel: senderDisplayName(selectedPhone, formData.from_phone_number),
      recipients: selectedContactIds.size,
      scheduleSummary: scheduleParts.join(" · "),
      paceSummary: `${formData.messages_per_minute} / minute · ${
        formData.max_messages_per_contact === 0
          ? "unlimited per contact"
          : `max ${formData.max_messages_per_contact} per contact`
      }`,
      message: formData.initial_message,
    });
    setConfirmOpen(true);
  };

  const handleConfirmSend = async () => {
    if (!pendingSend) return;
    try {
      await onSubmit(pendingSend.request, new Set(pendingSend.contactIds));
      setConfirmOpen(false);
    } catch {
      // The page layer already surfaces the error toast; keep the dialog open
      // so the send can be retried without re-entering the flow.
    }
  };

  return (
    <>
      <BaseCampaignWizard
        steps={steps}
        initialFormData={initialFormData}
        onSubmit={handleWizardSubmit}
        isSubmitting={isSubmitting}
        onCancel={onCancel}
        submitLabel="Send campaign"
        submittingLabel="Sending…"
        submitIcon={Send}
      />
      <SendConfirmationDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        campaignName={pendingSend?.campaignName ?? ""}
        senderLabel={pendingSend?.senderLabel ?? ""}
        recipients={pendingSend?.recipients ?? 0}
        scheduleSummary={pendingSend?.scheduleSummary ?? ""}
        paceSummary={pendingSend?.paceSummary ?? ""}
        message={pendingSend?.message ?? ""}
        isSending={isSubmitting}
        onConfirm={() => void handleConfirmSend()}
      />
    </>
  );
}
