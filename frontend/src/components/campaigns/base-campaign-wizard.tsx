"use client";

import { useCallback, useMemo } from "react";
import type { LucideIcon } from "lucide-react";

import { useWizard } from "@/hooks/useWizard";
import { BaseCampaignWizardLayout } from "./base-campaign-wizard-layout";
import type { WizardStep } from "./wizard-types";

export interface BaseCampaignWizardProps<
  TStepId extends string,
  TFormData extends object,
> {
  steps: ReadonlyArray<WizardStep<TStepId, TFormData>>;
  initialFormData: TFormData;
  onSubmit: (formData: TFormData) => void | Promise<void>;
  isSubmitting?: boolean;
  onCancel?: () => void;
  submitLabel?: string;
  submittingLabel?: string;
  submitIcon?: LucideIcon;
}

/**
 * Generic shell for campaign creation wizards. Each wizard only supplies a
 * typed list of steps with per-step render + validate callbacks; this
 * component owns navigation, validation aggregation, and the layout chrome.
 */
export function BaseCampaignWizard<
  TStepId extends string,
  TFormData extends object,
>({
  steps,
  initialFormData,
  onSubmit,
  isSubmitting = false,
  onCancel,
  submitLabel,
  submittingLabel,
  submitIcon,
}: BaseCampaignWizardProps<TStepId, TFormData>) {
  const stepDefs = useMemo(
    () => steps.map(({ id, label, icon }) => ({ id, label, icon })),
    [steps]
  );

  const validateStep = useCallback(
    (
      stepId: TStepId,
      data: TFormData,
      setErrors: React.Dispatch<React.SetStateAction<Record<string, string>>>
    ) => {
      const step = steps.find((s) => s.id === stepId);
      const result = step?.validate?.(data) ?? null;
      const nextErrors: Record<string, string> = {};
      if (result) {
        for (const [key, value] of Object.entries(result)) {
          if (typeof value === "string") nextErrors[key] = value;
        }
      }
      setErrors(nextErrors);
      return Object.keys(nextErrors).length === 0;
    },
    [steps]
  );

  const wizard = useWizard<TStepId, TFormData>({
    steps: stepDefs,
    initialFormData,
    validateStep,
  });

  const currentStep = steps.find((s) => s.id === wizard.currentStepId);

  const handleSubmit = useCallback(async () => {
    if (!wizard.validateAllSteps()) return;
    await onSubmit(wizard.formData);
  }, [wizard, onSubmit]);

  return (
    <BaseCampaignWizardLayout
      steps={stepDefs}
      wizard={wizard}
      onSubmit={handleSubmit}
      isSubmitting={isSubmitting}
      onCancel={onCancel}
      submitLabel={submitLabel}
      submittingLabel={submittingLabel}
      submitIcon={submitIcon}
    >
      {currentStep?.render({
        formData: wizard.formData,
        errors: wizard.errors,
        updateField: wizard.updateField,
      })}
    </BaseCampaignWizardLayout>
  );
}
