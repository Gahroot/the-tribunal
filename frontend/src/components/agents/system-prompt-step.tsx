"use client";

import type { UseFormReturn } from "react-hook-form";
import type { AgentFormValues } from "./create-agent-form";

import { Wand2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { BEST_PRACTICES_PROMPT } from "@/lib/voice-constants";

interface SystemPromptStepProps {
  form: UseFormReturn<AgentFormValues>;
}

export function SystemPromptStep({ form }: SystemPromptStepProps) {
  return (
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
  );
}
