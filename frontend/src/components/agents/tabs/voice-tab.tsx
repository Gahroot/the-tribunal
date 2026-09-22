import type { UseFormReturn } from "react-hook-form";

import type { EditAgentFormValues } from "@/components/agents/agent-edit-schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  REALTIME_MODEL_DEFAULT_VALUE,
  REALTIME_MODEL_OPTIONS,
} from "@/lib/agents/agent-voice";
import type { VoiceOption } from "@/lib/voice-constants";

interface VoiceTabProps {
  form: UseFormReturn<EditAgentFormValues>;
  voices: VoiceOption[];
}

export function VoiceTab({ form, voices }: VoiceTabProps) {
  return (
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
                <SelectContent className="max-h-[300px]">
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

        {form.watch("voiceProvider") === "openai" && (
          <FormField
            control={form.control}
            name="realtimeModel"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Realtime Model</FormLabel>
                <Select
                  onValueChange={(value) =>
                    field.onChange(value === REALTIME_MODEL_DEFAULT_VALUE ? null : value)
                  }
                  value={field.value ?? REALTIME_MODEL_DEFAULT_VALUE}
                >
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value={REALTIME_MODEL_DEFAULT_VALUE}>
                      Workspace default
                    </SelectItem>
                    {REALTIME_MODEL_OPTIONS.map((model) => (
                      <SelectItem key={model.id} value={model.id}>
                        {model.label} - {model.description}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormDescription>
                  Choose GPT Live (Realtime 2.1) for full-duplex conversation with background
                  reasoning. Workspace default is used when unset.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

        {form.watch("voiceProvider") === "openai" && isGptLiveModel(form.watch("realtimeModel")) && (
          <FormField
            control={form.control}
            name="reasoningEffort"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Reasoning Effort</FormLabel>
                <Select onValueChange={field.onChange} value={field.value}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value="minimal">Minimal - fastest, simplest turns</SelectItem>
                    <SelectItem value="low">Low - recommended default</SelectItem>
                    <SelectItem value="medium">Medium - deeper planning</SelectItem>
                    <SelectItem value="high">High - complex multi-step work</SelectItem>
                    <SelectItem value="xhigh">Extra high - maximum reasoning</SelectItem>
                  </SelectContent>
                </Select>
                <FormDescription>
                  How much GPT Live delegates to background reasoning. Higher effort improves hard
                  answers but adds latency and cost. Start with Low.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        )}
      </CardContent>
    </Card>
  );
}

/** Reasoning is only configurable on the gpt-realtime-2.x (GPT Live) models. */
function isGptLiveModel(model: string | null | undefined): boolean {
  return typeof model === "string" && model.startsWith("gpt-realtime-2");
}
