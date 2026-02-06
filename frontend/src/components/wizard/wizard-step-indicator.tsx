import { Check } from "lucide-react";
import type { WizardStepDef } from "@/hooks/useWizard";

interface WizardStepIndicatorProps<TStepId extends string> {
  steps: readonly WizardStepDef<TStepId>[];
  currentStepIndex: number;
  currentStepId: TStepId;
  onStepClick: (stepId: TStepId) => void;
}

export function WizardStepIndicator<TStepId extends string>({
  steps,
  currentStepIndex,
  currentStepId,
  onStepClick,
}: WizardStepIndicatorProps<TStepId>) {
  return (
    <div className="flex items-center justify-between px-6 py-4 border-b bg-muted/30">
      {steps.map((step, index) => {
        const Icon = step.icon;
        const isCompleted = index < currentStepIndex;
        const isCurrent = step.id === currentStepId;

        return (
          <button
            key={step.id}
            onClick={() => onStepClick(step.id)}
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
  );
}
