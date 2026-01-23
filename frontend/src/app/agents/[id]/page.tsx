"use client";

import { use, useState, useEffect, useRef, useMemo } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useWatch } from "react-hook-form";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import * as z from "zod";
import Link from "next/link";

import { agentsApi, type UpdateAgentRequest } from "@/lib/api/agents";
import { useWorkspaceId } from "@/hooks/use-workspace-id";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
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
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Slider } from "@/components/ui/slider";
import {
  AlertCircle,
  ArrowLeft,
  ChevronDown,
  Code2,
  Globe,
  Loader2,
  Search,
  Shield,
  ShieldAlert,
  AlertTriangle,
  Trash2,
  Wand2,
  Phone,
  MessageSquare,
  MessagesSquare,
  Headphones,
} from "lucide-react";
import { AVAILABLE_INTEGRATIONS, type ToolRiskLevel } from "@/lib/integrations";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { cn } from "@/lib/utils";
import { getLanguagesForTier } from "@/lib/languages";
import { VoiceTestDialog } from "@/components/agents/voice-test-dialog";
import { EmbedAgentDialog } from "@/components/agents/embed-agent-dialog";

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

// OpenAI Realtime API voices
const REALTIME_VOICES = [
  { id: "marin", name: "Marin", description: "Professional & clear" },
  { id: "cedar", name: "Cedar", description: "Natural & conversational" },
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
];

// Hume voices
const HUME_VOICES = [
  { id: "kora", name: "Kora", description: "Warm and professional" },
  { id: "melanie", name: "Melanie", description: "Natural and expressive" },
  { id: "aoede", name: "Aoede", description: "Clear and articulate" },
  { id: "orpheus", name: "Orpheus", description: "Rich and expressive" },
  { id: "charon", name: "Charon", description: "Deep and authoritative" },
  { id: "calliope", name: "Calliope", description: "Melodic and friendly" },
  { id: "atlas", name: "Atlas", description: "Strong and confident" },
  { id: "helios", name: "Helios", description: "Bright and energetic" },
  { id: "luna", name: "Luna", description: "Soft and calming" },
];

// Grok (xAI) voices - supports realism cues like [whisper], [sigh], [laugh]
const GROK_VOICES = [
  { id: "ara", name: "Ara", description: "Warm & friendly female" },
  { id: "rex", name: "Rex", description: "Confident & clear male" },
  { id: "sal", name: "Sal", description: "Smooth & balanced neutral" },
  { id: "eve", name: "Eve", description: "Energetic & upbeat female" },
  { id: "leo", name: "Leo", description: "Authoritative & strong male" },
];

// ElevenLabs voices - premium TTS with 100+ expressive voices
const ELEVENLABS_VOICES = [
  { id: "rachel", name: "Rachel", description: "Calm female" },
  { id: "bella", name: "Bella", description: "Soft female" },
  { id: "antoni", name: "Antoni", description: "Young male" },
  { id: "josh", name: "Josh", description: "Deep male" },
  { id: "adam", name: "Adam", description: "Narrator male" },
  { id: "sam", name: "Sam", description: "Raspy male" },
  { id: "domi", name: "Domi", description: "Strong female" },
  { id: "elli", name: "Elli", description: "Young female" },
  { id: "callum", name: "Callum", description: "Transatlantic male" },
  { id: "charlie", name: "Charlie", description: "Casual male" },
  { id: "charlotte", name: "Charlotte", description: "Swedish female" },
  { id: "daniel", name: "Daniel", description: "British male" },
  { id: "emily", name: "Emily", description: "Calm female" },
  { id: "freya", name: "Freya", description: "American female" },
  { id: "giovanni", name: "Giovanni", description: "Italian male" },
  { id: "grace", name: "Grace", description: "Southern female" },
  { id: "lily", name: "Lily", description: "British female" },
  { id: "matilda", name: "Matilda", description: "Warm female" },
  { id: "river", name: "River", description: "Confident female" },
  { id: "serena", name: "Serena", description: "Pleasant female" },
  { id: "thomas", name: "Thomas", description: "Calm male" },
];

// Grok built-in tools - these are native capabilities that auto-execute
const GROK_BUILTIN_TOOLS = [
  {
    id: "web_search",
    name: "Web Search",
    description:
      "Search the web for current events, prices, news, weather, and real-time information. Grok automatically decides when to search.",
  },
  {
    id: "x_search",
    name: "X (Twitter) Search",
    description:
      "Search X/Twitter for trending topics, public opinions, and recent posts. Great for understanding what people are saying.",
  },
];

// Get integrations that have tools defined
const INTEGRATIONS_WITH_TOOLS = AVAILABLE_INTEGRATIONS.filter(
  (i) => i.tools && i.tools.length > 0
);

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

const agentFormSchema = z.object({
  name: z.string().min(2, "Name must be at least 2 characters"),
  description: z.string().optional(),
  language: z.string().min(1, "Please select a language"),
  channelMode: z.enum(["voice", "text", "both"]),
  voiceProvider: z.string(),
  voiceId: z.string(),
  systemPrompt: z.string().min(10, "System prompt is required"),
  temperature: z.number().min(0).max(2),
  textResponseDelayMs: z.number().min(0).max(5000),
  textMaxContextMessages: z.number().min(1).max(50),
  calcomEventTypeId: z.number().optional().nullable(),
  isActive: z.boolean(),
  enabledTools: z.array(z.string()),
  enabledToolIds: z.record(z.string(), z.array(z.string())),
});

type AgentFormValues = z.infer<typeof agentFormSchema>;

// Map fields to their respective tabs for error tracking
const TAB_FIELDS: Record<string, (keyof AgentFormValues)[]> = {
  basic: ["name", "description", "language", "channelMode", "isActive"],
  voice: ["voiceProvider", "voiceId"],
  prompt: ["systemPrompt", "temperature"],
  tools: ["enabledTools", "enabledToolIds"],
  advanced: ["textResponseDelayMs", "textMaxContextMessages", "calcomEventTypeId"],
};

interface EditAgentPageProps {
  params: Promise<{ id: string }>;
}

export default function EditAgentPage({ params }: EditAgentPageProps) {
  const { id: agentId } = use(params);
  const router = useRouter();
  const queryClient = useQueryClient();
  const workspaceId = useWorkspaceId();
  const [activeTab, setActiveTab] = useState("basic");
  const [isDeleting, setIsDeleting] = useState(false);
  const [isVoiceTestOpen, setIsVoiceTestOpen] = useState(false);
  const [isEmbedDialogOpen, setIsEmbedDialogOpen] = useState(false);
  const isDeletingRef = useRef(false);

  const {
    data: agent,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["agent", workspaceId, agentId],
    queryFn: () => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      if (isDeletingRef.current) {
        return Promise.reject(new Error("Agent is being deleted"));
      }
      return agentsApi.get(workspaceId, agentId);
    },
    enabled: !!workspaceId && !isDeleting,
    retry: (failureCount, err) => {
      if (isDeletingRef.current) return false;
      if (err && typeof err === "object" && "response" in err) {
        const axiosError = err as { response?: { status?: number } };
        if (axiosError.response?.status === 404) {
          return false;
        }
      }
      return failureCount < 3;
    },
  });

  // Redirect to agents list when agent is not found (404)
  useEffect(() => {
    if (error && typeof error === "object" && "response" in error) {
      const axiosError = error as { response?: { status?: number } };
      if (axiosError.response?.status === 404) {
        toast.error("Agent not found or has been deleted");
        router.replace("/agents");
      }
    }
  }, [error, router]);

  const form = useForm<AgentFormValues>({
    resolver: zodResolver(agentFormSchema),
    defaultValues: {
      name: "",
      description: "",
      language: "en-US",
      channelMode: "voice",
      voiceProvider: "openai",
      voiceId: "marin",
      systemPrompt: "",
      temperature: 0.7,
      textResponseDelayMs: 0,
      textMaxContextMessages: 10,
      calcomEventTypeId: null,
      isActive: true,
      enabledTools: [],
      enabledToolIds: {},
    },
  });

  // Track if form has been initialized with agent data
  const formInitialized = useRef(false);

  // Reset form when agent data loads
  useEffect(() => {
    if (agent && !formInitialized.current) {
      formInitialized.current = true;
      form.reset({
        name: agent.name,
        description: agent.description ?? "",
        language: agent.language,
        channelMode: (agent.channel_mode as "voice" | "text" | "both") ?? "voice",
        voiceProvider: agent.voice_provider ?? "openai",
        voiceId: agent.voice_id ?? "marin",
        systemPrompt: agent.system_prompt,
        temperature: agent.temperature ?? 0.7,
        textResponseDelayMs: agent.text_response_delay_ms ?? 0,
        textMaxContextMessages: agent.text_max_context_messages ?? 10,
        calcomEventTypeId: agent.calcom_event_type_id,
        isActive: agent.is_active,
        enabledTools: agent.enabled_tools ?? [],
        enabledToolIds: agent.tool_settings ?? {},
      });
    }
  }, [agent, form]);

  // Get available languages
  const availableLanguages = useMemo(() => {
    return getLanguagesForTier("premium");
  }, []);

  // Watch voice provider to show appropriate voices
  const voiceProvider = form.watch("voiceProvider");
  const voices =
    voiceProvider === "grok"
      ? GROK_VOICES
      : voiceProvider === "hume"
        ? HUME_VOICES
        : voiceProvider === "elevenlabs"
          ? ELEVENLABS_VOICES
          : REALTIME_VOICES;

  // Reset voice when provider changes if current voice isn't valid
  useEffect(() => {
    const currentVoice = form.getValues("voiceId");
    const validVoiceIds = voices.map((v) => v.id);
    if (!validVoiceIds.includes(currentVoice)) {
      // Set default voice for provider
      const defaultVoice =
        voiceProvider === "grok"
          ? "ara"
          : voiceProvider === "hume"
            ? "kora"
            : voiceProvider === "elevenlabs"
              ? "rachel"
              : "marin";
      form.setValue("voiceId", defaultVoice);
    }
  }, [voiceProvider, voices, form]);

  // Watch tools for UI updates
  const enabledToolIds = useWatch({ control: form.control, name: "enabledToolIds" });

  const updateAgentMutation = useMutation({
    mutationFn: (data: UpdateAgentRequest) => {
      if (!workspaceId) throw new Error("Workspace not loaded");
      return agentsApi.update(workspaceId, agentId, data);
    },
  });

  // Handle delete
  const handleDeleteAgent = async () => {
    if (!workspaceId) {
      toast.error("Workspace not loaded");
      return;
    }

    isDeletingRef.current = true;
    setIsDeleting(true);

    void queryClient.cancelQueries({ queryKey: ["agent", workspaceId, agentId] });
    queryClient.removeQueries({ queryKey: ["agent", workspaceId, agentId] });

    try {
      await agentsApi.delete(workspaceId, agentId);
      toast.success("Agent deleted successfully");
      router.replace("/agents");
    } catch {
      toast.error("Failed to delete agent");
      router.replace("/agents");
    }
  };

  // Get error count for a specific tab
  const getTabErrorCount = (tabName: string): number => {
    const fields = TAB_FIELDS[tabName] ?? [];
    const errors = form.formState.errors;
    return fields.filter((field) => field in errors).length;
  };

  // Render tab trigger with optional error badge
  const TabTriggerWithErrors = ({ value, label }: { value: string; label: string }) => {
    const errorCount = getTabErrorCount(value);
    return (
      <TabsTrigger
        value={value}
        onClick={() => setActiveTab(value)}
        className={cn(errorCount > 0 && "text-destructive")}
      >
        {label}
        {errorCount > 0 && (
          <span className="ml-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[10px] font-medium text-destructive-foreground">
            {errorCount}
          </span>
        )}
      </TabsTrigger>
    );
  };

  async function onSubmit(data: AgentFormValues) {
    const request: UpdateAgentRequest = {
      name: data.name,
      description: data.description || undefined,
      language: data.language,
      channel_mode: data.channelMode,
      voice_provider: data.voiceProvider,
      voice_id: data.voiceId,
      system_prompt: data.systemPrompt,
      temperature: data.temperature,
      text_response_delay_ms: data.textResponseDelayMs,
      text_max_context_messages: data.textMaxContextMessages,
      calcom_event_type_id: data.calcomEventTypeId ?? undefined,
      is_active: data.isActive,
      enabled_tools: data.enabledTools,
      tool_settings: data.enabledToolIds,
    };

    try {
      await updateAgentMutation.mutateAsync(request);
      toast.success("Agent updated successfully");
      await queryClient.invalidateQueries({ queryKey: ["agents", workspaceId] });
      await queryClient.invalidateQueries({ queryKey: ["agent", workspaceId, agentId] });
      router.push("/agents");
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Failed to update agent";
      toast.error(errorMessage);
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !agent) {
    const is404 =
      error &&
      typeof error === "object" &&
      "response" in error &&
      (error as { response?: { status?: number } }).response?.status === 404;

    if (is404) {
      return (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      );
    }

    return (
      <div className="space-y-6 p-6">
        <Button variant="ghost" asChild>
          <Link href="/agents">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Agents
          </Link>
        </Button>
        <Card className="border-destructive">
          <CardContent className="flex flex-col items-center justify-center py-16">
            <AlertCircle className="mb-4 h-16 w-16 text-destructive" />
            <h3 className="mb-2 text-lg font-semibold">Error loading agent</h3>
            <p className="mb-4 text-center text-sm text-muted-foreground">
              {error instanceof Error ? error.message : "Failed to load agent details"}
            </p>
            <Button asChild>
              <Link href="/agents">Return to Agents</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" className="h-8 w-8" asChild>
            <Link href="/agents">
              <ArrowLeft className="h-4 w-4" />
            </Link>
          </Button>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-semibold">{agent.name}</h1>
            <Badge variant={agent.is_active ? "default" : "secondary"} className="h-5 text-[10px]">
              {agent.is_active ? "Active" : "Inactive"}
            </Badge>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-8"
            onClick={() => setIsVoiceTestOpen(true)}
          >
            <Headphones className="mr-1.5 h-3.5 w-3.5" />
            Test Voice
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-8"
            onClick={() => setIsEmbedDialogOpen(true)}
          >
            <Code2 className="mr-1.5 h-3.5 w-3.5" />
            Embed
          </Button>
          <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="destructive" size="sm" className="h-8">
              <Trash2 className="mr-1.5 h-3.5 w-3.5" />
              Delete
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle className="text-destructive">
                Delete &ldquo;{agent.name}&rdquo;?
              </AlertDialogTitle>
              <AlertDialogDescription>
                This action cannot be undone. This will permanently delete the agent and all
                associated data.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={(e) => {
                  e.preventDefault();
                  void handleDeleteAgent();
                }}
                disabled={isDeleting}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {isDeleting ? "Deleting..." : "Delete Permanently"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>

      <VoiceTestDialog
        open={isVoiceTestOpen}
        onOpenChange={setIsVoiceTestOpen}
        agentId={agentId}
        agentName={agent.name}
        workspaceId={workspaceId ?? ""}
      />

      <EmbedAgentDialog
        open={isEmbedDialogOpen}
        onOpenChange={setIsEmbedDialogOpen}
        agentId={agentId}
        agentName={agent.name}
        workspaceId={workspaceId ?? ""}
      />

      <Form {...form}>
        <form
          onSubmit={(e) => {
            void form.handleSubmit(onSubmit)(e);
          }}
          className="space-y-4"
        >
          <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
            <TabsList>
              <TabTriggerWithErrors value="basic" label="Basic" />
              <TabTriggerWithErrors value="voice" label="Voice" />
              <TabTriggerWithErrors value="prompt" label="AI Prompt" />
              <TabTriggerWithErrors value="tools" label="Tools" />
              <TabTriggerWithErrors value="advanced" label="Advanced" />
            </TabsList>

            <TabsContent value="basic" className="mt-4 space-y-3">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium">Basic Information</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid gap-3 md:grid-cols-2">
                    <FormField
                      control={form.control}
                      name="name"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Agent Name</FormLabel>
                          <FormControl>
                            <Input placeholder="Customer Support Agent" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="language"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Language</FormLabel>
                          <Select onValueChange={field.onChange} value={field.value}>
                            <FormControl>
                              <SelectTrigger>
                                <SelectValue placeholder="Select a language" />
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
                  </div>

                  <FormField
                    control={form.control}
                    name="description"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Description</FormLabel>
                        <FormControl>
                          <Textarea
                            placeholder="Handles customer inquiries and support"
                            className="min-h-[80px]"
                            {...field}
                          />
                        </FormControl>
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
                        <FormDescription>
                          Select which communication channels this agent supports
                        </FormDescription>
                        <div className="grid grid-cols-3 gap-3 pt-2">
                          {[
                            {
                              value: "voice",
                              label: "Voice Only",
                              description: "Phone calls only",
                              icon: Phone,
                            },
                            {
                              value: "text",
                              label: "Text Only",
                              description: "SMS/text messages only",
                              icon: MessageSquare,
                            },
                            {
                              value: "both",
                              label: "Voice & Text",
                              description: "Both channels",
                              icon: MessagesSquare,
                            },
                          ].map((option) => {
                            const Icon = option.icon;
                            const isSelected = field.value === option.value;
                            return (
                              <button
                                key={option.value}
                                type="button"
                                onClick={() => field.onChange(option.value)}
                                className={`flex flex-col items-center gap-2 rounded-lg border-2 p-4 text-center transition-colors ${
                                  isSelected
                                    ? "border-primary bg-primary/5"
                                    : "border-border hover:border-primary/50"
                                }`}
                              >
                                <Icon
                                  className={`h-6 w-6 ${isSelected ? "text-primary" : "text-muted-foreground"}`}
                                />
                                <div>
                                  <p
                                    className={`text-sm font-medium ${isSelected ? "text-primary" : ""}`}
                                  >
                                    {option.label}
                                  </p>
                                  <p className="text-xs text-muted-foreground">
                                    {option.description}
                                  </p>
                                </div>
                              </button>
                            );
                          })}
                        </div>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="isActive"
                    render={({ field }) => (
                      <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                          <FormLabel className="text-base">Active Status</FormLabel>
                          <FormDescription>Enable or disable this agent</FormDescription>
                        </div>
                        <FormControl>
                          <Switch checked={field.value} onCheckedChange={field.onChange} />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="voice" className="mt-4 space-y-3">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium">Voice Settings</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <FormField
                    control={form.control}
                    name="voiceProvider"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Voice Provider</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="openai">
                              <div className="flex flex-col">
                                <span>OpenAI Realtime</span>
                                <span className="text-xs text-muted-foreground">
                                  Best voice quality, fastest response
                                </span>
                              </div>
                            </SelectItem>
                            <SelectItem value="grok">
                              <div className="flex flex-col">
                                <span>Grok (xAI)</span>
                                <span className="text-xs text-muted-foreground">
                                  Built-in web & X search, realism cues
                                </span>
                              </div>
                            </SelectItem>
                            <SelectItem value="hume">
                              <div className="flex flex-col">
                                <span>Hume AI</span>
                                <span className="text-xs text-muted-foreground">
                                  Emotion-aware voice synthesis
                                </span>
                              </div>
                            </SelectItem>
                            <SelectItem value="elevenlabs">
                              <div className="flex flex-col">
                                <span>ElevenLabs</span>
                                <span className="text-xs text-muted-foreground">
                                  Most expressive, 100+ premium voices
                                </span>
                              </div>
                            </SelectItem>
                          </SelectContent>
                        </Select>
                        <FormDescription>
                          {field.value === "grok"
                            ? "Grok includes built-in search tools and supports realism cues like [whisper], [sigh], [laugh]"
                            : field.value === "hume"
                              ? "Hume AI provides emotional intelligence in voice synthesis"
                              : field.value === "elevenlabs"
                                ? "ElevenLabs provides the most expressive TTS with 100+ premium voices"
                                : "OpenAI Realtime offers the best voice quality and lowest latency"}
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="voiceId"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Voice</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder="Select a voice" />
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
                        <FormDescription>
                          The voice your agent will use for speech synthesis
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>

              {/* Grok-specific built-in tools */}
              {voiceProvider === "grok" && (
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-sm font-medium">
                      Grok Built-in Search Tools
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <p className="text-sm text-muted-foreground">
                      Grok has built-in search capabilities that execute automatically during
                      conversations. Enable the ones you want your agent to use.
                    </p>
                    <FormField
                      control={form.control}
                      name="enabledTools"
                      render={({ field }) => (
                        <div className="space-y-3">
                          {GROK_BUILTIN_TOOLS.map((tool) => {
                            const isEnabled = field.value?.includes(tool.id);
                            const Icon = tool.id === "web_search" ? Globe : Search;
                            return (
                              <div
                                key={tool.id}
                                className={cn(
                                  "flex items-start gap-3 rounded-lg border p-4 transition-colors",
                                  isEnabled && "border-primary bg-primary/5"
                                )}
                              >
                                <Checkbox
                                  checked={isEnabled}
                                  onCheckedChange={(checked) => {
                                    const current = field.value ?? [];
                                    if (checked) {
                                      field.onChange([...current, tool.id]);
                                    } else {
                                      field.onChange(current.filter((v) => v !== tool.id));
                                    }
                                  }}
                                />
                                <div className="flex-1 space-y-1">
                                  <div className="flex items-center gap-2">
                                    <Icon className="h-4 w-4 text-muted-foreground" />
                                    <span className="font-medium">{tool.name}</span>
                                    <Badge variant="secondary" className="text-xs">
                                      Auto
                                    </Badge>
                                  </div>
                                  <p className="text-sm text-muted-foreground">
                                    {tool.description}
                                  </p>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    />
                  </CardContent>
                </Card>
              )}
            </TabsContent>

            <TabsContent value="prompt" className="mt-4 space-y-3">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium">AI Configuration</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center justify-between rounded-lg border border-dashed bg-muted/50 p-3">
                    <div>
                      <p className="text-sm font-medium">Need help writing a prompt?</p>
                      <p className="text-xs text-muted-foreground">
                        Start with our best practices template
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
                      const isTooLong = charCount > 2000;
                      return (
                        <FormItem>
                          <div className="flex items-center justify-between">
                            <FormLabel>System Prompt</FormLabel>
                            <span
                              className={cn(
                                "text-xs",
                                isOptimal && "text-green-600",
                                isTooShort && "text-yellow-600",
                                isTooLong && "text-destructive"
                              )}
                            >
                              {charCount.toLocaleString()} characters
                              {isTooShort && " (recommended: 100+)"}
                              {isTooLong && " (recommended: under 2,000)"}
                            </span>
                          </div>
                          <FormControl>
                            <Textarea
                              placeholder="You are a helpful customer support agent..."
                              className="min-h-[200px] font-mono text-sm"
                              {...field}
                            />
                          </FormControl>
                          <FormDescription>
                            Instructions that define your agent&apos;s personality and behavior
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      );
                    }}
                  />

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
                              {field.value?.toFixed(1) ?? "0.7"} (
                              {getTemperatureLabel(field.value ?? 0.7)})
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
                          <FormDescription>
                            Lower values produce more focused and deterministic responses
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      );
                    }}
                  />
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="tools" className="mt-4 space-y-3">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium">Tools & Integrations</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm text-muted-foreground">
                    Enable integrations and select which tools your agent can access. High-risk
                    tools are disabled by default for security.
                  </p>

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
            </TabsContent>

            <TabsContent value="advanced" className="mt-4 space-y-3">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium">Text Agent Settings</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <FormField
                    control={form.control}
                    name="textResponseDelayMs"
                    render={({ field }) => (
                      <FormItem>
                        <div className="flex items-center justify-between">
                          <FormLabel>Response Delay</FormLabel>
                          <span className="text-sm font-medium">{field.value}ms</span>
                        </div>
                        <FormControl>
                          <Slider
                            min={0}
                            max={5000}
                            step={100}
                            value={[field.value]}
                            onValueChange={(value) => field.onChange(value[0])}
                            className="w-full"
                          />
                        </FormControl>
                        <FormDescription>
                          Delay before sending text responses (makes it feel more natural)
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="textMaxContextMessages"
                    render={({ field }) => (
                      <FormItem>
                        <div className="flex items-center justify-between">
                          <FormLabel>Max Context Messages</FormLabel>
                          <span className="text-sm font-medium">{field.value}</span>
                        </div>
                        <FormControl>
                          <Slider
                            min={1}
                            max={50}
                            step={1}
                            value={[field.value]}
                            onValueChange={(value) => field.onChange(value[0])}
                            className="w-full"
                          />
                        </FormControl>
                        <FormDescription>
                          Number of previous messages to include for context
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium">Calendar Integration</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <FormField
                    control={form.control}
                    name="calcomEventTypeId"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Cal.com Event Type ID</FormLabel>
                        <FormControl>
                          <Input
                            type="number"
                            placeholder="Enter Event Type ID"
                            value={field.value ?? ""}
                            onChange={(e) => {
                              const value = e.target.value
                                ? parseInt(e.target.value)
                                : null;
                              field.onChange(value);
                            }}
                          />
                        </FormControl>
                        <FormDescription>
                          Optional: Connect to Cal.com for appointment booking
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium">Agent Statistics</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
                    <div className="rounded-md border p-3">
                      <p className="text-xs text-muted-foreground">Provider</p>
                      <p className="text-sm font-medium capitalize">{agent.voice_provider}</p>
                    </div>
                    <div className="rounded-md border p-3">
                      <p className="text-xs text-muted-foreground">Created</p>
                      <p className="text-sm font-medium">
                        {new Date(agent.created_at).toLocaleDateString()}
                      </p>
                    </div>
                    <div className="rounded-md border p-3">
                      <p className="text-xs text-muted-foreground">Last Updated</p>
                      <p className="text-sm font-medium">
                        {new Date(agent.updated_at).toLocaleDateString()}
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>

          <Separator />

          <div className="flex justify-end gap-3">
            <Button
              type="button"
              variant="outline"
              size="sm"
              asChild
              disabled={updateAgentMutation.isPending}
            >
              <Link href="/agents">Cancel</Link>
            </Button>
            <Button type="submit" size="sm" disabled={updateAgentMutation.isPending}>
              {updateAgentMutation.isPending ? "Saving..." : "Save Changes"}
            </Button>
          </div>
        </form>
      </Form>
    </div>
  );
}
