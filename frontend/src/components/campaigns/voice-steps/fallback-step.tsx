"use client";

import { MessageSquare } from "lucide-react";

import { SMSFallbackStep, type SMSFallbackMode } from "../sms-fallback-step";
import type { WizardStep } from "../wizard-types";
import type { Agent } from "@/types";

export interface SMSFallbackStepFields {
  sms_fallback_enabled: boolean;
  sms_fallback_mode: SMSFallbackMode;
  sms_fallback_template: string;
  sms_fallback_agent_id?: string;
}

/**
 * Voice-specific step: configures the SMS fallback sent when the call
 * fails to reach a human (voicemail, no-answer, busy).
 */
export function makeFallbackStep<
  TStepId extends string,
  TFormData extends SMSFallbackStepFields,
>(opts: {
  id: TStepId;
  textAgents: Agent[];
}): WizardStep<TStepId, TFormData> {
  return {
    id: opts.id,
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
      if (data.sms_fallback_mode === "ai" && !data.sms_fallback_agent_id) {
        errors.agentId = "Select an agent for AI-generated messages";
      }
      return errors;
    },
    render: ({ formData, errors, updateField }) => {
      const setField = <K extends keyof SMSFallbackStepFields>(
        key: K,
        value: SMSFallbackStepFields[K],
      ) =>
        updateField(
          key as unknown as keyof TFormData,
          value as unknown as TFormData[keyof TFormData],
        );

      return (
        <SMSFallbackStep
          enabled={formData.sms_fallback_enabled}
          onEnabledChange={(v) => setField("sms_fallback_enabled", v)}
          mode={formData.sms_fallback_mode}
          onModeChange={(v) => setField("sms_fallback_mode", v)}
          template={formData.sms_fallback_template}
          onTemplateChange={(v) => setField("sms_fallback_template", v)}
          agentId={formData.sms_fallback_agent_id}
          onAgentChange={(v) => setField("sms_fallback_agent_id", v)}
          agents={opts.textAgents}
          errors={errors}
        />
      );
    },
  };
}
