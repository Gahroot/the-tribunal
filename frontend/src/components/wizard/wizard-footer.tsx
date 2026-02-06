import { ArrowLeft, ArrowRight, Loader2, Send } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";

interface WizardFooterProps {
  isFirstStep: boolean;
  isLastStep: boolean;
  onPrevious: () => void;
  onNext: () => void;
  onSubmit: () => void;
  isSubmitting?: boolean;
  onCancel?: () => void;
  submitLabel?: string;
  submittingLabel?: string;
  submitIcon?: LucideIcon;
}

export function WizardFooter({
  isFirstStep,
  isLastStep,
  onPrevious,
  onNext,
  onSubmit,
  isSubmitting = false,
  onCancel,
  submitLabel = "Submit",
  submittingLabel = "Creating...",
  submitIcon: SubmitIcon = Send,
}: WizardFooterProps) {
  return (
    <div className="flex items-center justify-between px-6 py-4 border-t bg-background">
      <div>
        {onCancel && (
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
      <div className="flex items-center gap-2">
        {!isFirstStep && (
          <Button variant="outline" onClick={onPrevious}>
            <ArrowLeft className="size-4 mr-2" />
            Previous
          </Button>
        )}
        {!isLastStep ? (
          <Button onClick={onNext}>
            Next
            <ArrowRight className="size-4 ml-2" />
          </Button>
        ) : (
          <Button onClick={onSubmit} disabled={isSubmitting}>
            {isSubmitting ? (
              <>
                <Loader2 className="size-4 mr-2 animate-spin" />
                {submittingLabel}
              </>
            ) : (
              <>
                <SubmitIcon className="size-4 mr-2" />
                {submitLabel}
              </>
            )}
          </Button>
        )}
      </div>
    </div>
  );
}
