import type { UseFormReturn } from "react-hook-form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Wand2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { BEST_PRACTICES_PROMPT } from "@/lib/voice-constants";
import type { EditAgentFormValues } from "@/components/agents/agent-edit-schema";

interface PromptTabProps {
  form: UseFormReturn<EditAgentFormValues>;
}

export function PromptTab({ form }: PromptTabProps) {
  return (
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
  );
}
