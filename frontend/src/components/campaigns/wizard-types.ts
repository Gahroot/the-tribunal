import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

export type WizardErrors = Record<string, string>;

export interface WizardStepRenderArgs<TFormData extends object> {
  formData: TFormData;
  errors: WizardErrors;
  updateField: <K extends keyof TFormData>(key: K, value: TFormData[K]) => void;
}

export interface WizardStep<TStepId extends string, TFormData extends object> {
  id: TStepId;
  label: string;
  icon: LucideIcon;
  render: (args: WizardStepRenderArgs<TFormData>) => ReactNode;
  validate?: (formData: TFormData) => Readonly<Record<string, string | undefined>> | null;
}
