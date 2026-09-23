"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  Bot,
  Check,
  ClipboardCheck,
  Loader2,
  MessageSquare,
  Mic,
  Play,
  Sparkles,
  Wrench,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useMemo, useEffect, Fragment } from "react";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Form } from "@/components/ui/form";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import {
  CREATE_AGENT_FORM_DEFAULTS,
  buildCreateAgentRequest,
  createAgentFormSchema,
  type CreateAgentFormValues,
} from "@/lib/agents/agent-form";
import {
  getVoiceProviderForTier,
  resolveVoiceForProvider,
} from "@/lib/agents/agent-voice";
import { agentsApi, type Agent, type CreateAgentRequest } from "@/lib/api/agents";
import { getLanguagesForTier, getFallbackLanguage } from "@/lib/languages";
import { PRICING_TIERS } from "@/lib/pricing-tiers";
import { queryKeys } from "@/lib/query-keys";
import { cn } from "@/lib/utils";
import { getApiErrorMessage } from "@/lib/utils/errors";

import { JobStep } from "./job-step";
import { LimitsNotice } from "./limits-notice";
import { SettingsReviewStep } from "./settings-review-step";
import { StartingPointStep } from "./starting-point-step";
import { SystemPromptStep } from "./system-prompt-step";
import { ToolsIntegrationsStep } from "./tools-integrations-step";
import { VoiceLanguageStep } from "./voice-language-step";

/**
 * Wizard steps, in order. `label` is the compact progress-chip text;
 * `title` is the fuller question shown in the header line.
 */
const WIZARD_STEPS = [
  { id: 1, label: "Job", title: "What does this agent do?", icon: Bot },
  { id: 2, label: "Start", title: "Pick a starting point", icon: Sparkles },
  { id: 3, label: "Voice", title: "Voice & language", icon: Mic },
  { id: 4, label: "Prompt", title: "Prompt", icon: MessageSquare },
  { id: 5, label: "Tools", title: "Tools", icon: Wrench },
  { id: 6, label: "Review", title: "Review & create", icon: ClipboardCheck },
] as const;

export type AgentFormValues = CreateAgentFormValues;

export function CreateAgentForm() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();
  const [step, setStep] = useState(1);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [createdAgent, setCreatedAgent] = useState<Agent | null>(null);
  const [startingPointId, setStartingPointId] = useState("scratch");
  const [limitsDismissed, setLimitsDismissed] = useState(false);

  const createAgentMutation = useMutation({
    mutationFn: (data: CreateAgentRequest) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return agentsApi.create(workspaceId, data);
    },
    onSuccess: (agent) => {
      if (workspaceId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.agents.all(workspaceId) });
      }
      toast.success("Agent created successfully!");
      setCreatedAgent(agent);
    },
    onError: (error) => {
      toast.error(getApiErrorMessage(error, "Failed to create agent. Please try again."));
      setIsSubmitting(false);
    },
  });

  const form = useForm<AgentFormValues>({
    resolver: zodResolver(createAgentFormSchema),
    defaultValues: CREATE_AGENT_FORM_DEFAULTS,
  });

  const pricingTier = useWatch({ control: form.control, name: "pricingTier" });
  const enabledTools = useWatch({ control: form.control, name: "enabledTools" });
  const enabledToolIds = useWatch({ control: form.control, name: "enabledToolIds" });
  const agentName = useWatch({ control: form.control, name: "name" });
  const agentDescription = useWatch({ control: form.control, name: "description" });
  const systemPrompt = useWatch({ control: form.control, name: "systemPrompt" });
  const currentLanguage = useWatch({ control: form.control, name: "language" });

  const selectedTier = useMemo(
    () => PRICING_TIERS.find((t) => t.id === pricingTier),
    [pricingTier]
  );

  const availableLanguages = useMemo(
    () => getLanguagesForTier(pricingTier),
    [pricingTier]
  );

  // Reset language if invalid for new tier
  useEffect(() => {
    const fallback = getFallbackLanguage(currentLanguage, pricingTier);
    if (fallback !== currentLanguage) {
      form.setValue("language", fallback);
    }
  }, [pricingTier, currentLanguage, form]);

  // Set default voice when pricing tier changes
  useEffect(() => {
    const provider = getVoiceProviderForTier(pricingTier);
    const currentVoice = form.getValues("voice");
    const resolved = resolveVoiceForProvider(provider, currentVoice);
    if (resolved !== currentVoice) {
      form.setValue("voice", resolved);
    }
  }, [pricingTier, form]);

  // Zod/React Hook Form rules, mapped to the new step order. The full schema
  // still runs on submit via form.handleSubmit.
  const validateStep = async (currentStep: number): Promise<boolean> => {
    switch (currentStep) {
      case 1:
        // Job: name + one-sentence purpose.
        return form.trigger(["name", "description"]);
      case 2:
        // Starting point: "scratch" is preselected, nothing required.
        return true;
      case 3:
        // Voice & language.
        return form.trigger(["language", "voice", "channelMode"]);
      case 4:
        // Prompt.
        return form.trigger(["systemPrompt", "initialGreeting"]);
      case 5:
        // Tools: nothing required.
        return true;
      case 6:
        // Review: full-schema validation runs on Create.
        return true;
      default:
        return true;
    }
  };

  const handleNext = async () => {
    const isValid = await validateStep(step);
    if (isValid && step < WIZARD_STEPS.length) {
      setStep(step + 1);
    }
  };

  const handleBack = () => {
    if (step > 1) {
      setStep(step - 1);
    } else {
      router.push("/agents");
    }
  };

  const handleSubmit = (data: AgentFormValues) => {
    if (isSubmitting) return;
    setIsSubmitting(true);

    const apiRequest: CreateAgentRequest = buildCreateAgentRequest(data);
    createAgentMutation.mutate(apiRequest);
  };

  if (createdAgent) {
    return (
      <div className="min-h-screen">
        <div className="mx-auto max-w-xl p-6 pt-16 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full">
            <Check className="h-7 w-7 text-success" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight">
            {createdAgent.name} is ready
          </h1>
          <p className="mt-2 text-muted-foreground">
            Rehearse it against built-in prospect personas in the Practice Arena
            before it talks to real leads: no live sends, just a scored report.
          </p>
          <div className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
            <Button asChild>
              <Link href={`/agents/practice?agentId=${createdAgent.id}`}>
                <Sparkles className="mr-2 h-4 w-4" />
                Test in Practice Arena
              </Link>
            </Button>
            <Button variant="outline" asChild>
              <Link href="/agents">Go to Agents</Link>
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <div className="mx-auto max-w-4xl p-6">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold tracking-tight">Create Voice Agent</h1>
          <p className="text-muted-foreground">
            Step {step} of {WIZARD_STEPS.length} &middot;{" "}
            {WIZARD_STEPS[step - 1]?.title ?? ""}
          </p>
        </div>

        {/* Dismissible limits/upgrade notice — pricing lives here, not in a wizard step */}
        {!limitsDismissed && selectedTier && (
          <LimitsNotice
            tier={selectedTier}
            onDismiss={() => setLimitsDismissed(true)}
          />
        )}

        {/* Progress Bar */}
        <div className="mb-6">
          <div className="grid grid-cols-[1fr_1rem_1fr_1rem_1fr_1rem_1fr_1rem_1fr_1rem_1fr] items-center">
            {WIZARD_STEPS.map((s, idx) => {
              const Icon = s.icon;
              const isActive = s.id === step;
              const isCompleted = s.id < step;

              return (
                <Fragment key={s.id}>
                  <button
                    type="button"
                    onClick={() => s.id < step && setStep(s.id)}
                    disabled={s.id > step}
                    className={cn(
                      "relative z-10 flex items-center gap-2 rounded-lg border p-2 transition-all duration-300",
                      isActive && "border-primary bg-secondary",
                      isCompleted && "cursor-pointer border-primary bg-secondary hover:bg-muted",
                      !isActive && !isCompleted && "cursor-not-allowed border-border bg-muted/30"
                    )}
                  >
                    <div
                      className={cn(
                        "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-medium transition-all",
                        isActive && "bg-primary text-primary-foreground",
                        isCompleted && "bg-primary text-primary-foreground",
                        !isActive && !isCompleted && "bg-muted text-muted-foreground"
                      )}
                    >
                      {isCompleted ? (
                        <Check className="h-3 w-3" />
                      ) : (
                        <Icon className="h-3 w-3" />
                      )}
                    </div>
                    <span
                      className={cn(
                        "hidden text-xs font-medium sm:block",
                        isActive && "text-foreground",
                        isCompleted && "text-foreground",
                        !isActive && !isCompleted && "text-muted-foreground"
                      )}
                    >
                      {s.label}
                    </span>
                  </button>

                  {idx < WIZARD_STEPS.length - 1 && (
                    <div className="relative h-0.5">
                      <div className="absolute inset-0 bg-border" />
                      {isCompleted && (
                        <div className="absolute inset-0 bg-primary" />
                      )}
                    </div>
                  )}
                </Fragment>
              );
            })}
          </div>
        </div>

        {/* Form Content */}
        <Form {...form}>
          <form onSubmit={(e) => e.preventDefault()} className="space-y-6">
            {step === 1 && <JobStep form={form} />}
            {step === 2 && (
              <StartingPointStep
                form={form}
                selectedId={startingPointId}
                onSelect={setStartingPointId}
              />
            )}
            {step === 3 && (
              <VoiceLanguageStep
                form={form}
                pricingTier={pricingTier}
                availableLanguages={availableLanguages}
              />
            )}
            {step === 4 && <SystemPromptStep form={form} />}
            {step === 5 && <ToolsIntegrationsStep form={form} pricingTier={pricingTier} enabledToolIds={enabledToolIds} />}
            {step === 6 && (
              <SettingsReviewStep
                form={form}
                pricingTier={pricingTier}
                agentName={agentName}
                agentDescription={agentDescription}
                systemPrompt={systemPrompt}
                enabledTools={enabledTools}
                selectedTier={selectedTier}
              />
            )}

            {/* Navigation */}
            <div className="flex items-center justify-between border-t pt-6">
              <Button
                type="button"
                variant="outline"
                onClick={handleBack}
              >
                <ArrowLeft className="mr-2 h-4 w-4" />
                {step === 1 ? "Cancel" : "Back"}
              </Button>

              {step < WIZARD_STEPS.length ? (
                <Button type="button" onClick={() => void handleNext()}>
                  Next
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              ) : (
                <Button
                  type="button"
                  onClick={() => void form.handleSubmit(handleSubmit)()}
                  disabled={isSubmitting}
                >
                  {isSubmitting ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Play className="mr-2 h-4 w-4" />
                  )}
                  {isSubmitting ? "Creating..." : "Create Agent"}
                </Button>
              )}
            </div>
          </form>
        </Form>
      </div>
    </div>
  );
}
