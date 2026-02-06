import { useState, useMemo, useCallback, useRef, useEffect } from "react";
import type { LucideIcon } from "lucide-react";

export interface WizardStepDef<TStepId extends string> {
  id: TStepId;
  label: string;
  icon: LucideIcon;
}

type SetErrors = React.Dispatch<React.SetStateAction<Record<string, string>>>;

export interface UseWizardOptions<TStepId extends string, TFormData extends object> {
  steps: readonly WizardStepDef<TStepId>[];
  initialFormData: TFormData;
  validateStep?: (stepId: TStepId, formData: TFormData, setErrors: SetErrors) => boolean;
  validateOnNavigate?: boolean;
}

export interface UseWizardReturn<TStepId extends string, TFormData extends object> {
  currentStepId: TStepId;
  currentStepIndex: number;
  isFirstStep: boolean;
  isLastStep: boolean;
  formData: TFormData;
  errors: Record<string, string>;
  setErrors: SetErrors;
  goToStep: (stepId: TStepId) => void;
  goNext: () => void;
  goPrevious: () => void;
  validateAllSteps: () => boolean;
  updateField: <K extends keyof TFormData>(key: K, value: TFormData[K]) => void;
}

export function useWizard<TStepId extends string, TFormData extends object>({
  steps,
  initialFormData,
  validateStep,
  validateOnNavigate = true,
}: UseWizardOptions<TStepId, TFormData>): UseWizardReturn<TStepId, TFormData> {
  const [currentStepId, setCurrentStepId] = useState<TStepId>(steps[0].id);
  const [formData, setFormData] = useState<TFormData>(initialFormData);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Store validateStep in a ref so navigation always calls the latest version
  const validateStepRef = useRef(validateStep);
  useEffect(() => {
    validateStepRef.current = validateStep;
  }, [validateStep]);

  // Store formData in a ref so callbacks always have the latest version
  const formDataRef = useRef(formData);
  useEffect(() => {
    formDataRef.current = formData;
  }, [formData]);

  const currentStepIndex = useMemo(
    () => steps.findIndex((s) => s.id === currentStepId),
    [steps, currentStepId]
  );

  const isFirstStep = currentStepIndex === 0;
  const isLastStep = currentStepIndex === steps.length - 1;

  const runValidation = useCallback(
    (stepId: TStepId): boolean => {
      if (!validateStepRef.current) return true;
      return validateStepRef.current(stepId, formDataRef.current, setErrors);
    },
    []
  );

  const goToStep = useCallback(
    (stepId: TStepId) => {
      const targetIndex = steps.findIndex((s) => s.id === stepId);
      if (validateOnNavigate && targetIndex > currentStepIndex) {
        if (!runValidation(currentStepId)) return;
      }
      setCurrentStepId(stepId);
    },
    [steps, currentStepIndex, currentStepId, validateOnNavigate, runValidation]
  );

  const goNext = useCallback(() => {
    if (validateOnNavigate) {
      if (!runValidation(currentStepId)) return;
    }
    const nextIndex = currentStepIndex + 1;
    if (nextIndex < steps.length) {
      setCurrentStepId(steps[nextIndex].id);
    }
  }, [steps, currentStepIndex, currentStepId, validateOnNavigate, runValidation]);

  const goPrevious = useCallback(() => {
    const prevIndex = currentStepIndex - 1;
    if (prevIndex >= 0) {
      setCurrentStepId(steps[prevIndex].id);
    }
  }, [steps, currentStepIndex]);

  const validateAllSteps = useCallback((): boolean => {
    if (!validateStepRef.current) return true;
    for (const step of steps) {
      if (!validateStepRef.current(step.id, formDataRef.current, setErrors)) {
        setCurrentStepId(step.id);
        return false;
      }
    }
    return true;
  }, [steps]);

  const updateField = useCallback(
    <K extends keyof TFormData>(key: K, value: TFormData[K]) => {
      setFormData((prev) => ({ ...prev, [key]: value }));
      setErrors((prev) => {
        if (prev[key as string]) {
          const next = { ...prev };
          delete next[key as string];
          return next;
        }
        return prev;
      });
    },
    []
  );

  return {
    currentStepId,
    currentStepIndex,
    isFirstStep,
    isLastStep,
    formData,
    errors,
    setErrors,
    goToStep,
    goNext,
    goPrevious,
    validateAllSteps,
    updateField,
  };
}
