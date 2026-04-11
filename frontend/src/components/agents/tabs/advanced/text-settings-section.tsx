import type { Control } from "react-hook-form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Slider } from "@/components/ui/slider";
import type { EditAgentFormValues } from "@/components/agents/agent-edit-schema";

interface TextSettingsSectionProps {
  control: Control<EditAgentFormValues>;
}

export function TextSettingsSection({ control }: TextSettingsSectionProps) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium">Text Agent Settings</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <FormField
          control={control}
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
          control={control}
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
  );
}
