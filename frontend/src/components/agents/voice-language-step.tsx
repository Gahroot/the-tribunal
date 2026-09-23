"use client";

import type { UseFormReturn } from "react-hook-form";

import { Card, CardContent } from "@/components/ui/card";
import {
  FormControl,
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
  REALTIME_VOICES,
  HUME_VOICES,
  GROK_VOICES,
  ELEVENLABS_VOICES,
} from "@/lib/voice-constants";

import type { AgentFormValues } from "./create-agent-form";

interface VoiceLanguageStepProps {
  form: UseFormReturn<AgentFormValues>;
  pricingTier: string;
  availableLanguages: Array<{ code: string; name: string }>;
}

/**
 * Step 3 — voice & language. Split out of the old combined basics step so the
 * wizard can lead with the agent's job instead.
 */
export function VoiceLanguageStep({
  form,
  pricingTier,
  availableLanguages,
}: VoiceLanguageStepProps) {
  return (
    <Card>
      <CardContent className="space-y-4 p-6">
        <div className="mb-2">
          <h2 className="text-lg font-medium">Voice &amp; language</h2>
          <p className="text-sm text-muted-foreground">
            Choose the language, channels, and voice your agent speaks with.
          </p>
        </div>

        <FormField
          control={form.control}
          name="voice"
          render={({ field }) => {
            const voices =
              pricingTier === "grok"
                ? GROK_VOICES
                : pricingTier === "openai-hume"
                  ? HUME_VOICES
                  : pricingTier === "elevenlabs"
                    ? ELEVENLABS_VOICES
                    : REALTIME_VOICES;
            return (
              <FormItem>
                <FormLabel>Voice</FormLabel>
                <Select onValueChange={field.onChange} value={field.value}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select voice" />
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
                <FormMessage />
              </FormItem>
            );
          }}
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
                    <SelectItem value="both">Voice &amp; Text</SelectItem>
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>
      </CardContent>
    </Card>
  );
}
