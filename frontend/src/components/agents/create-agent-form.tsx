"use client";

import { useState, useMemo, useEffect, Fragment } from "react";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useWatch } from "react-hook-form";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import * as z from "zod";

import { agentsApi, type CreateAgentRequest } from "@/lib/api/agents";
import { useAuth } from "@/providers/auth-provider";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Sparkles,
  Zap,
  Crown,
  Bot,
  MessageSquare,
  Wrench,
  Settings,
  Play,
  Wand2,
  ChevronDown,
  AlertTriangle,
  Shield,
  ShieldAlert,
  Loader2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Card, CardContent } from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";

import { PRICING_TIERS } from "@/lib/pricing-tiers";
import { getLanguagesForTier, getFallbackLanguage } from "@/lib/languages";
import { AVAILABLE_INTEGRATIONS, type ToolRiskLevel } from "@/lib/integrations";
import { cn } from "@/lib/utils";

// OpenAI Realtime API voices (for Premium tier)
const REALTIME_VOICES = [
  { id: "marin", name: "Marin", description: "Professional & clear (Recommended)", recommended: true },
  { id: "cedar", name: "Cedar", description: "Natural & conversational (Recommended)", recommended: true },
  { id: "alloy", name: "Alloy", description: "Neutral and balanced" },
  { id: "ash", name: "Ash", description: "Clear and precise" },
  { id: "ballad", name: "Ballad", description: "Melodic and smooth" },
  { id: "coral", name: "Coral", description: "Warm and friendly" },
  { id: "echo", name: "Echo", description: "Warm and engaging" },
  { id: "fable", name: "Fable", description: "Expressive and dramatic" },
  { id: "nova", name: "Nova", description: "Friendly and upbeat" },
  { id: "onyx", name: "Onyx", description: "Deep and authoritative" },
  { id: "sage", name: "Sage", description: "Calm and thoughtful" },
  { id: "shimmer", name: "Shimmer", description: "Energetic and expressive" },
  { id: "verse", name: "Verse", description: "Versatile and expressive" },
] as const;

// Hume Octave voices (for openai-hume tier)
const HUME_VOICES = [
  { id: "kora", name: "Kora", description: "Warm and professional (Recommended)", recommended: true },
  { id: "melanie", name: "Melanie", description: "Natural and expressive (Recommended)", recommended: true },
  { id: "aoede", name: "Aoede", description: "Clear and articulate" },
  { id: "orpheus", name: "Orpheus", description: "Rich and expressive" },
  { id: "charon", name: "Charon", description: "Deep and authoritative" },
  { id: "calliope", name: "Calliope", description: "Melodic and friendly" },
  { id: "atlas", name: "Atlas", description: "Strong and confident" },
  { id: "helios", name: "Helios", description: "Bright and energetic" },
  { id: "luna", name: "Luna", description: "Soft and calming" },
] as const;

// Get integrations that have tools defined
const INTEGRATIONS_WITH_TOOLS = AVAILABLE_INTEGRATIONS.filter(
  (i) => i.tools && i.tools.length > 0
);

// Best practices system prompt template
const BEST_PRACTICES_PROMPT = `# Role & Identity
You are a helpful phone assistant for [COMPANY_NAME]. You help customers with questions, support requests, and general inquiries.

# Personality & Tone
- Warm, concise, and confident—never fawning or overly enthusiastic
- Keep responses to 2-3 sentences maximum
- Speak at a steady, unhurried pace
- Use occasional natural fillers like "let me check that" for conversational flow

# Language Rules
- ALWAYS respond in the same language the customer uses
- If audio is unclear, say: "Sorry, I didn't catch that. Could you repeat?"
- Never switch languages mid-conversation unless asked

# Turn-Taking
- Wait for the customer to finish speaking before responding
- Use brief acknowledgments: "Got it," "I understand," "Let me help with that"
- Vary your responses—never repeat the same phrase twice in a row

# Alphanumeric Handling
- When reading back phone numbers, spell digit by digit: "4-1-5-5-5-5-1-2-3-4"
- For confirmation codes, say each character separately
- Always confirm: "Just to verify, that's [X]. Is that correct?"

# Tool Usage
- For lookups: Call immediately, say "Let me check that for you"
- For changes: Confirm first: "I'll update that now. Is that correct?"

# Escalation
Transfer to a human when:
- Customer explicitly requests it
- Customer expresses frustration
- You cannot resolve their issue after 2 attempts
- Request is outside your capabilities

# Boundaries
- Stay focused on [COMPANY_NAME] services
- If unsure, say: "Let me transfer you to someone who can help with that"
- Be honest when you don't know something`;

// Helper to get risk level badge variant and icon
function getRiskLevelBadge(level: ToolRiskLevel) {
  switch (level) {
    case "safe":
      return { variant: "outline" as const, icon: Shield, color: "text-green-600" };
    case "moderate":
      return { variant: "outline" as const, icon: AlertTriangle, color: "text-yellow-600" };
    case "high":
      return { variant: "outline" as const, icon: ShieldAlert, color: "text-red-600" };
  }
}

const WIZARD_STEPS = [
  { id: 1, label: "Pricing", icon: Sparkles },
  { id: 2, label: "Basics", icon: Bot },
  { id: 3, label: "Prompt", icon: MessageSquare },
  { id: 4, label: "Tools", icon: Wrench },
  { id: 5, label: "Settings", icon: Settings },
] as const;

const agentFormSchema = z.object({
  pricingTier: z.enum(["budget", "balanced", "premium-mini", "premium", "hume-evi", "openai-hume"]),
  name: z.string().min(2, "Name must be at least 2 characters"),
  description: z.string().optional(),
  language: z.string(),
  voice: z.string(),
  channelMode: z.enum(["voice", "text", "both"]),
  systemPrompt: z.string().min(10, "System prompt is required"),
  initialGreeting: z.string().optional(),
  temperature: z.number().min(0).max(2),
  maxTokens: z.number().min(100).max(16000),
  enabledTools: z.array(z.string()),
  enabledToolIds: z.record(z.string(), z.array(z.string())),
  enableRecording: z.boolean(),
  enableTranscript: z.boolean(),
});

type AgentFormValues = z.infer<typeof agentFormSchema>;

export function CreateAgentForm() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { workspaceId } = useAuth();
  const [step, setStep] = useState(1);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const createAgentMutation = useMutation({
    mutationFn: (data: CreateAgentRequest) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return agentsApi.create(workspaceId, data);
    },
    onSuccess: () => {
      if (workspaceId) {
        queryClient.invalidateQueries({ queryKey: ["agents", workspaceId] });
      }
      toast.success("Agent created successfully!");
      router.push("/agents");
    },
    onError: (error) => {
      console.error("Failed to create agent:", error);
      toast.error("Failed to create agent. Please try again.");
      setIsSubmitting(false);
    },
  });

  const form = useForm<AgentFormValues>({
    resolver: zodResolver(agentFormSchema),
    defaultValues: {
      name: "",
      description: "",
      systemPrompt: "",
      initialGreeting: "",
      pricingTier: "premium",
      language: "en-US",
      voice: "marin",
      channelMode: "both",
      temperature: 0.7,
      maxTokens: 2000,
      enabledTools: [],
      enabledToolIds: {},
      enableRecording: true,
      enableTranscript: true,
    },
  });

  const pricingTier = useWatch({ control: form.control, name: "pricingTier" });
  const enabledTools = useWatch({ control: form.control, name: "enabledTools" });
  const enabledToolIds = useWatch({ control: form.control, name: "enabledToolIds" });
  const agentName = useWatch({ control: form.control, name: "name" });
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

  const validateStep = async (currentStep: number): Promise<boolean> => {
    switch (currentStep) {
      case 1: {
        const selectedTierId = form.getValues("pricingTier");
        const tier = PRICING_TIERS.find((t) => t.id === selectedTierId);
        return !tier?.underConstruction;
      }
      case 2:
        return form.trigger(["name"]);
      case 3:
        return form.trigger("systemPrompt");
      case 4:
        return true;
      case 5:
        return true;
      default:
        return true;
    }
  };

  const handleNext = async () => {
    const isValid = await validateStep(step);
    if (isValid && step < 5) {
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

    // Map form data to API request format
    const apiRequest: CreateAgentRequest = {
      name: data.name,
      description: data.description || undefined,
      channel_mode: data.channelMode,
      voice_provider: data.pricingTier === "openai-hume" ? "hume" : "openai",
      voice_id: data.voice,
      language: data.language,
      system_prompt: data.systemPrompt,
      temperature: data.temperature,
      enabled_tools: data.enabledTools,
      tool_settings: data.enabledToolIds,
    };

    createAgentMutation.mutate(apiRequest);
  };

  const getTierIcon = (tierId: string) => {
    switch (tierId) {
      case "budget":
        return Zap;
      case "premium":
        return Crown;
      default:
        return Sparkles;
    }
  };

  return (
    <div className="min-h-screen">
      <div className="mx-auto max-w-4xl p-6">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold tracking-tight">Create Voice Agent</h1>
          <p className="text-muted-foreground">
            Step {step} of 5 &middot; {WIZARD_STEPS[step - 1]?.label ?? ""}
          </p>
        </div>

        {/* Progress Bar */}
        <div className="mb-6">
          <div className="grid grid-cols-[1fr_1rem_1fr_1rem_1fr_1rem_1fr_1rem_1fr] items-center">
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
                      isActive && "border-primary bg-primary/10 ring-1 ring-primary",
                      isCompleted && "cursor-pointer border-primary bg-primary/5 hover:bg-primary/10",
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
            {/* Step 1: Pricing Tier */}
            {step === 1 && (
              <Card>
                <CardContent className="p-6">
                  <div className="mb-4">
                    <h2 className="text-lg font-medium">Choose Your Pricing Tier</h2>
                    <p className="text-sm text-muted-foreground">
                      Select the right balance of cost and quality for your use case
                    </p>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {PRICING_TIERS.map((tier) => {
                      const TierIcon = getTierIcon(tier.id);
                      const isSelected = pricingTier === tier.id;

                      return (
                        <button
                          key={tier.id}
                          type="button"
                          disabled={tier.underConstruction}
                          onClick={() =>
                            !tier.underConstruction &&
                            form.setValue("pricingTier", tier.id as AgentFormValues["pricingTier"])
                          }
                          className={cn(
                            "relative flex flex-col rounded-lg border p-4 text-left transition-all",
                            tier.underConstruction
                              ? "cursor-not-allowed opacity-60"
                              : "hover:border-primary/50",
                            isSelected &&
                              !tier.underConstruction &&
                              "border-primary bg-primary/5 ring-2 ring-primary"
                          )}
                        >
                          {tier.recommended && (
                            <Badge className="absolute -top-2 right-3 text-[10px]">Popular</Badge>
                          )}
                          <div className="mb-3 flex items-center gap-2">
                            <div
                              className={cn(
                                "flex h-8 w-8 items-center justify-center rounded-md",
                                isSelected ? "bg-primary text-primary-foreground" : "bg-muted"
                              )}
                            >
                              <TierIcon className="h-4 w-4" />
                            </div>
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="font-medium">{tier.name}</span>
                                {tier.underConstruction && (
                                  <Badge variant="secondary" className="px-1.5 py-0 text-[9px]">
                                    Coming Soon
                                  </Badge>
                                )}
                              </div>
                              <div className="text-xs text-muted-foreground">
                                ${tier.costPerHour.toFixed(2)}/hr
                              </div>
                            </div>
                          </div>
                          <p className="mb-3 text-xs text-muted-foreground">{tier.description}</p>
                          <div className="space-y-1 text-xs">
                            <div className="flex items-center justify-between">
                              <span className="text-muted-foreground">Speed</span>
                              <span className="font-medium">{tier.performance.speed}</span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-muted-foreground">Quality</span>
                              <span className="font-medium">{tier.performance.quality}</span>
                            </div>
                            <div className="flex items-center justify-between">
                              <span className="text-muted-foreground">Model</span>
                              <span className="font-mono text-[10px]">{tier.config.llmModel}</span>
                            </div>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Step 2: Basic Info */}
            {step === 2 && (
              <Card>
                <CardContent className="space-y-4 p-6">
                  <div className="mb-2">
                    <h2 className="text-lg font-medium">Basic Information</h2>
                    <p className="text-sm text-muted-foreground">
                      Give your agent a name and identity
                    </p>
                  </div>

                  <FormField
                    control={form.control}
                    name="name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Agent Name *</FormLabel>
                        <FormControl>
                          <Input placeholder="e.g., Sarah" {...field} />
                        </FormControl>
                        <FormDescription>A friendly name to identify your agent</FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="description"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Description</FormLabel>
                        <FormControl>
                          <Textarea
                            placeholder="Handles customer inquiries and support requests..."
                            className="min-h-[80px]"
                            {...field}
                          />
                        </FormControl>
                        <FormDescription>Optional description for your reference</FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <div className="grid gap-4 sm:grid-cols-2">
                    <FormField
                      control={form.control}
                      name="language"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Language ({availableLanguages.length} available)</FormLabel>
                          <Select onValueChange={field.onChange} value={field.value}>
                            <FormControl>
                              <SelectTrigger>
                                <SelectValue />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent className="max-h-[300px]">
                              {availableLanguages.map((lang) => (
                                <SelectItem key={lang.code} value={lang.code}>
                                  {lang.name}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="channelMode"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Channel Mode</FormLabel>
                          <Select onValueChange={field.onChange} value={field.value}>
                            <FormControl>
                              <SelectTrigger>
                                <SelectValue />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              <SelectItem value="voice">Voice Only</SelectItem>
                              <SelectItem value="text">Text Only</SelectItem>
                              <SelectItem value="both">Voice & Text</SelectItem>
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>

                  {(pricingTier === "premium" ||
                    pricingTier === "premium-mini" ||
                    pricingTier === "openai-hume") && (
                    <FormField
                      control={form.control}
                      name="voice"
                      render={({ field }) => {
                        const voices = pricingTier === "openai-hume" ? HUME_VOICES : REALTIME_VOICES;
                        return (
                          <FormItem>
                            <FormLabel>Voice</FormLabel>
                            <Select onValueChange={field.onChange} value={field.value}>
                              <FormControl>
                                <SelectTrigger>
                                  <SelectValue placeholder="Select voice" />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                {voices.map((voice) => (
                                  <SelectItem key={voice.id} value={voice.id}>
                                    {voice.name} - {voice.description}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            <FormMessage />
                          </FormItem>
                        );
                      }}
                    />
                  )}
                </CardContent>
              </Card>
            )}

            {/* Step 3: System Prompt */}
            {step === 3 && (
              <Card>
                <CardContent className="space-y-4 p-6">
                  <div className="flex items-start justify-between">
                    <div className="mb-2">
                      <h2 className="text-lg font-medium">System Prompt</h2>
                      <p className="text-sm text-muted-foreground">
                        Define your agent&apos;s personality and behavior
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => form.setValue("systemPrompt", BEST_PRACTICES_PROMPT)}
                      className="shrink-0"
                    >
                      <Wand2 className="mr-1.5 h-3.5 w-3.5" />
                      Use Best Practices
                    </Button>
                  </div>

                  <FormField
                    control={form.control}
                    name="systemPrompt"
                    render={({ field }) => {
                      const charCount = field.value?.length ?? 0;
                      const isOptimal = charCount >= 100 && charCount <= 2000;
                      const isTooShort = charCount > 0 && charCount < 100;

                      return (
                        <FormItem>
                          <div className="flex items-center justify-between">
                            <FormLabel>Instructions *</FormLabel>
                            <span
                              className={cn(
                                "text-xs",
                                isOptimal && "text-green-600",
                                isTooShort && "text-yellow-600"
                              )}
                            >
                              {charCount} characters
                              {isTooShort && " (aim for 100+)"}
                            </span>
                          </div>
                          <FormControl>
                            <Textarea
                              placeholder={`You are a helpful customer support agent for [Company Name].

Your role:
- Answer questions about our products and services
- Help customers troubleshoot issues
- Be polite, professional, and concise`}
                              className="min-h-[300px] font-mono text-sm"
                              {...field}
                            />
                          </FormControl>
                          <FormDescription>
                            Tell your agent who they are, how to behave, and what rules to follow.
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      );
                    }}
                  />

                  <FormField
                    control={form.control}
                    name="initialGreeting"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Initial Greeting (Optional)</FormLabel>
                        <FormControl>
                          <Textarea
                            placeholder="Hello! Thank you for calling. How can I help you today?"
                            className="min-h-[80px]"
                            {...field}
                          />
                        </FormControl>
                        <FormDescription>
                          What the agent says when the call starts. Leave empty for a natural start.
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>
            )}

            {/* Step 4: Tools */}
            {step === 4 && (
              <Card>
                <CardContent className="space-y-4 p-6">
                  <div className="mb-2">
                    <h2 className="text-lg font-medium">Tools & Integrations</h2>
                    <p className="text-sm text-muted-foreground">
                      Enable integrations and select which tools your agent can access. High-risk
                      tools are disabled by default for security.
                    </p>
                  </div>

                  <div className="space-y-3">
                    {INTEGRATIONS_WITH_TOOLS.map((integration) => (
                      <FormField
                        key={integration.id}
                        control={form.control}
                        name="enabledTools"
                        render={({ field }) => {
                          const isEnabled = field.value?.includes(integration.id);
                          return (
                            <Collapsible>
                              <div className="rounded-lg border">
                                <div className="flex items-center justify-between p-4">
                                  <div className="flex items-center space-x-3">
                                    <Checkbox
                                      checked={isEnabled}
                                      onCheckedChange={(checked) => {
                                        const current = field.value ?? [];
                                        if (checked) {
                                          field.onChange([...current, integration.id]);
                                          // Auto-enable default tools
                                          const defaultTools =
                                            integration.tools
                                              ?.filter((t) => t.defaultEnabled)
                                              .map((t) => t.id) ?? [];
                                          if (defaultTools.length > 0) {
                                            const currentToolIds = form.getValues("enabledToolIds") ?? {};
                                            form.setValue("enabledToolIds", {
                                              ...currentToolIds,
                                              [integration.id]: defaultTools,
                                            });
                                          }
                                        } else {
                                          field.onChange(current.filter((v) => v !== integration.id));
                                          // Clear tool selection
                                          const currentToolIds = form.getValues("enabledToolIds") ?? {};
                                          // eslint-disable-next-line @typescript-eslint/no-unused-vars
                                          const { [integration.id]: _removed, ...rest } = currentToolIds;
                                          form.setValue("enabledToolIds", rest);
                                        }
                                      }}
                                    />
                                    <div>
                                      <div className="flex items-center gap-2">
                                        <span className="font-medium">{integration.name}</span>
                                        {integration.isBuiltIn && (
                                          <Badge variant="secondary" className="text-xs">
                                            Built-in
                                          </Badge>
                                        )}
                                      </div>
                                      <p className="text-sm text-muted-foreground">
                                        {integration.description}
                                      </p>
                                    </div>
                                  </div>
                                  {isEnabled && integration.tools && integration.tools.length > 0 && (
                                    <CollapsibleTrigger asChild>
                                      <Button type="button" variant="ghost" size="sm">
                                        <ChevronDown className="h-4 w-4" />
                                        <span className="ml-1">
                                          {enabledToolIds?.[integration.id]?.length ?? 0} /{" "}
                                          {integration.tools.length} tools
                                        </span>
                                      </Button>
                                    </CollapsibleTrigger>
                                  )}
                                </div>

                                {isEnabled && integration.tools && integration.tools.length > 0 && (
                                  <CollapsibleContent>
                                    <div className="border-t bg-muted/30 p-4">
                                      <div className="mb-3 flex items-center justify-between">
                                        <span className="text-sm font-medium">Available Tools</span>
                                        <div className="flex gap-2">
                                          <Button
                                            type="button"
                                            variant="outline"
                                            size="sm"
                                            onClick={() => {
                                              const allToolIds = integration.tools?.map((t) => t.id) ?? [];
                                              const currentToolIds = form.getValues("enabledToolIds") ?? {};
                                              form.setValue("enabledToolIds", {
                                                ...currentToolIds,
                                                [integration.id]: allToolIds,
                                              });
                                            }}
                                          >
                                            Select All
                                          </Button>
                                          <Button
                                            type="button"
                                            variant="outline"
                                            size="sm"
                                            onClick={() => {
                                              const currentToolIds = form.getValues("enabledToolIds") ?? {};
                                              form.setValue("enabledToolIds", {
                                                ...currentToolIds,
                                                [integration.id]: [],
                                              });
                                            }}
                                          >
                                            Clear All
                                          </Button>
                                        </div>
                                      </div>
                                      <div className="space-y-2">
                                        {integration.tools.map((tool) => {
                                          const riskBadge = getRiskLevelBadge(tool.riskLevel);
                                          const RiskIcon = riskBadge.icon;
                                          const currentTools = enabledToolIds?.[integration.id] ?? [];
                                          const isToolEnabled = currentTools.includes(tool.id);
                                          return (
                                            <div
                                              key={tool.id}
                                              className="flex items-center justify-between rounded-md border bg-background p-3"
                                            >
                                              <div className="flex items-center space-x-3">
                                                <Checkbox
                                                  checked={isToolEnabled}
                                                  onCheckedChange={(checked) => {
                                                    const allToolIds = form.getValues("enabledToolIds") ?? {};
                                                    const toolsForIntegration = allToolIds[integration.id] ?? [];
                                                    const newTools = checked
                                                      ? [...toolsForIntegration, tool.id]
                                                      : toolsForIntegration.filter((t) => t !== tool.id);
                                                    form.setValue("enabledToolIds", {
                                                      ...allToolIds,
                                                      [integration.id]: newTools,
                                                    });
                                                  }}
                                                />
                                                <div>
                                                  <span className="text-sm font-medium">{tool.name}</span>
                                                  <p className="text-xs text-muted-foreground">
                                                    {tool.description}
                                                  </p>
                                                </div>
                                              </div>
                                              <Badge variant={riskBadge.variant} className={riskBadge.color}>
                                                <RiskIcon className="mr-1 h-3 w-3" />
                                                {tool.riskLevel}
                                              </Badge>
                                            </div>
                                          );
                                        })}
                                      </div>
                                    </div>
                                  </CollapsibleContent>
                                )}
                              </div>
                            </Collapsible>
                          );
                        }}
                      />
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Step 5: Settings & Review */}
            {step === 5 && (
              <div className="space-y-4">
                <Card>
                  <CardContent className="space-y-4 p-6">
                    <div className="mb-2">
                      <h2 className="text-lg font-medium">Call Settings</h2>
                      <p className="text-sm text-muted-foreground">
                        Configure recording and transcription
                      </p>
                    </div>

                    <FormField
                      control={form.control}
                      name="enableRecording"
                      render={({ field }) => (
                        <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                          <div className="space-y-0.5">
                            <FormLabel className="text-sm font-medium">Call Recording</FormLabel>
                            <FormDescription className="text-xs">
                              Record all calls for quality assurance
                            </FormDescription>
                          </div>
                          <FormControl>
                            <Switch checked={field.value} onCheckedChange={field.onChange} />
                          </FormControl>
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="enableTranscript"
                      render={({ field }) => (
                        <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                          <div className="space-y-0.5">
                            <FormLabel className="text-sm font-medium">Transcripts</FormLabel>
                            <FormDescription className="text-xs">
                              Save searchable conversation transcripts
                            </FormDescription>
                          </div>
                          <FormControl>
                            <Switch checked={field.value} onCheckedChange={field.onChange} />
                          </FormControl>
                        </FormItem>
                      )}
                    />
                  </CardContent>
                </Card>

                <Card>
                  <CardContent className="space-y-4 p-6">
                    <div className="mb-2">
                      <h2 className="text-lg font-medium">AI Settings</h2>
                      <p className="text-sm text-muted-foreground">
                        Fine-tune the AI response behavior
                      </p>
                    </div>

                    <div className="grid gap-4 sm:grid-cols-2">
                      <FormField
                        control={form.control}
                        name="temperature"
                        render={({ field }) => {
                          const getTemperatureLabel = (value: number) => {
                            if (value <= 0.3) return "Focused";
                            if (value <= 0.7) return "Balanced";
                            if (value <= 1.2) return "Creative";
                            return "Very Creative";
                          };
                          return (
                            <FormItem>
                              <div className="flex items-center justify-between">
                                <FormLabel>Temperature</FormLabel>
                                <span className="text-sm font-medium">
                                  {field.value?.toFixed(1) ?? "0.7"} ({getTemperatureLabel(field.value ?? 0.7)})
                                </span>
                              </div>
                              <FormControl>
                                <div className="space-y-2">
                                  <Slider
                                    min={0}
                                    max={2}
                                    step={0.1}
                                    value={[field.value ?? 0.7]}
                                    onValueChange={(value) => field.onChange(value[0])}
                                    className="w-full"
                                  />
                                  <div className="flex justify-between text-xs text-muted-foreground">
                                    <span>Focused</span>
                                    <span>Creative</span>
                                  </div>
                                </div>
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          );
                        }}
                      />

                      <FormField
                        control={form.control}
                        name="maxTokens"
                        render={({ field }) => (
                          <FormItem>
                            <div className="flex items-center justify-between">
                              <FormLabel>Max Tokens</FormLabel>
                              <span className="text-sm font-medium">
                                {(field.value ?? 2000).toLocaleString()}
                              </span>
                            </div>
                            <FormControl>
                              <div className="space-y-2">
                                <Slider
                                  min={100}
                                  max={4000}
                                  step={100}
                                  value={[field.value ?? 2000]}
                                  onValueChange={(value) => field.onChange(value[0])}
                                  className="w-full"
                                />
                                <div className="flex justify-between text-xs text-muted-foreground">
                                  <span>100</span>
                                  <span>4,000</span>
                                </div>
                              </div>
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>
                  </CardContent>
                </Card>

                {/* Summary Card */}
                <Card className="border-primary/30 bg-primary/5">
                  <CardContent className="p-6">
                    <h2 className="mb-4 text-lg font-medium">Review Your Agent</h2>

                    <div className="grid gap-4 sm:grid-cols-2">
                      <div className="space-y-3">
                        <div>
                          <p className="text-xs text-muted-foreground">Name</p>
                          <p className="font-medium">{agentName || "Not set"}</p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">Pricing Tier</p>
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{selectedTier?.name}</span>
                            <Badge variant="outline" className="text-[10px]">
                              ${selectedTier?.costPerHour.toFixed(2)}/hr
                            </Badge>
                          </div>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">AI Model</p>
                          <p className="font-mono text-sm">{selectedTier?.config.llmModel}</p>
                        </div>
                      </div>

                      <div className="space-y-3">
                        <div>
                          <p className="text-xs text-muted-foreground">System Prompt</p>
                          <p className="text-sm">
                            {systemPrompt
                              ? `${systemPrompt.slice(0, 80)}${systemPrompt.length > 80 ? "..." : ""}`
                              : "Not set"}
                          </p>
                        </div>
                        <div>
                          <p className="text-xs text-muted-foreground">Tools Enabled</p>
                          <p className="font-medium">
                            {enabledTools.length > 0
                              ? `${enabledTools.length} integration${enabledTools.length > 1 ? "s" : ""}`
                              : "None"}
                          </p>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
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

              {step < 5 ? (
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
