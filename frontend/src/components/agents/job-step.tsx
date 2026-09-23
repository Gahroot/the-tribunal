"use client";

import type { UseFormReturn } from "react-hook-form";

import { Card, CardContent } from "@/components/ui/card";
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

import type { AgentFormValues } from "./create-agent-form";

interface JobStepProps {
  form: UseFormReturn<AgentFormValues>;
}

/**
 * Step 1 — the agent's job. Leads the wizard with what the agent does
 * (name + one-sentence purpose) instead of pricing.
 */
export function JobStep({ form }: JobStepProps) {
  return (
    <Card>
      <CardContent className="space-y-4 p-6">
        <div className="mb-2">
          <h2 className="text-lg font-medium">What does this agent do?</h2>
          <p className="text-sm text-muted-foreground">
            Start with the job, not the settings. Name your agent and describe its purpose in
            one sentence.
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
              <FormLabel>Purpose</FormLabel>
              <FormControl>
                <Textarea
                  placeholder="e.g., Qualifies inbound leads and books showings for our listing team"
                  className="min-h-[80px]"
                  {...field}
                />
              </FormControl>
              <FormDescription>
                One sentence is enough; the full instructions come in the prompt step.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
      </CardContent>
    </Card>
  );
}
