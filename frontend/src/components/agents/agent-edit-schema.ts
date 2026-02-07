import * as z from "zod";

export const editAgentFormSchema = z.object({
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
  // IVR navigation settings (Grok only)
  enableIvrNavigation: z.boolean(),
  ivrNavigationGoal: z.string().optional(),
  ivrLoopThreshold: z.number().min(1).max(10),
  ivrSilenceDurationMs: z.number().min(1000).max(10000),
  ivrPostDtmfCooldownMs: z.number().min(0).max(10000),
  ivrMenuBufferSilenceMs: z.number().min(0).max(10000),
  // Appointment reminder settings
  reminderEnabled: z.boolean(),
  reminderMinutesBefore: z.number().min(5).max(1440),
  // Experiment auto-evaluation
  autoEvaluate: z.boolean(),
});

export type EditAgentFormValues = z.infer<typeof editAgentFormSchema>;

// Map fields to their respective tabs for error tracking
export const TAB_FIELDS: Record<string, (keyof EditAgentFormValues)[]> = {
  basic: ["name", "description", "language", "channelMode", "isActive"],
  voice: ["voiceProvider", "voiceId"],
  prompt: ["systemPrompt", "temperature"],
  tools: ["enabledTools", "enabledToolIds"],
  advanced: ["textResponseDelayMs", "textMaxContextMessages", "calcomEventTypeId", "reminderEnabled", "reminderMinutesBefore", "autoEvaluate"],
};
