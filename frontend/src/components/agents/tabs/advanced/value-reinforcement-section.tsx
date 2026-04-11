import { type Control, useWatch } from "react-hook-form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Switch } from "@/components/ui/switch";
import type { EditAgentFormValues } from "@/components/agents/agent-edit-schema";

interface ValueReinforcementSectionProps {
  control: Control<EditAgentFormValues>;
}

const VR_TEMPLATE_PLACEHOLDER =
  "Hi {first_name}, just a reminder that your appointment is tomorrow on {appointment_date} at {appointment_time}. We're looking forward to seeing you — reply here if you have any questions!";

export function ValueReinforcementSection({ control }: ValueReinforcementSectionProps) {
  const vrEnabled = useWatch({ control, name: "valueReinforcementEnabled" });
  const vrTemplate = useWatch({ control, name: "valueReinforcementTemplate" }) ?? "";
  const vrCharCount = vrTemplate.length;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium">Value-Reinforcement Message</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <FormField
          control={control}
          name="valueReinforcementEnabled"
          render={({ field }) => (
            <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
              <div className="space-y-0.5">
                <FormLabel className="text-base">Enable Value-Reinforcement SMS</FormLabel>
                <FormDescription>
                  Send a pre-appointment SMS to re-engage and excite the contact before they show up
                </FormDescription>
              </div>
              <FormControl>
                <Switch checked={field.value} onCheckedChange={field.onChange} />
              </FormControl>
            </FormItem>
          )}
        />

        {vrEnabled && (
          <>
            <FormField
              control={control}
              name="valueReinforcementOffsetMinutes"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Minutes before appointment</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      min={1}
                      max={10080}
                      placeholder="120"
                      value={field.value}
                      onChange={(e) => field.onChange(parseInt(e.target.value) || 120)}
                    />
                  </FormControl>
                  <FormDescription>
                    How many minutes before the appointment to send this message (e.g. 120 = 2 hours before).
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={control}
              name="valueReinforcementTemplate"
              render={({ field }) => (
                <FormItem>
                  <div className="flex items-center justify-between">
                    <FormLabel>Value-Reinforcement Message</FormLabel>
                    <span
                      className={`text-xs ${vrCharCount > 160 ? "text-amber-600 font-medium" : "text-muted-foreground"}`}
                    >
                      {vrCharCount} / 160
                      {vrCharCount > 160 ? ` (${Math.ceil(vrCharCount / 153)} segments)` : ""}
                    </span>
                  </div>
                  <FormControl>
                    <Textarea
                      placeholder={VR_TEMPLATE_PLACEHOLDER}
                      className="min-h-[90px] font-mono text-sm resize-none"
                      value={field.value ?? ""}
                      onChange={(e) => field.onChange(e.target.value || null)}
                    />
                  </FormControl>
                  <FormDescription>
                    A message sent before the appointment to build excitement and reduce no-shows. Supports{" "}
                    <code className="text-xs font-mono bg-muted rounded px-1">{"{first_name}"}</code>,{" "}
                    <code className="text-xs font-mono bg-muted rounded px-1">{"{appointment_date}"}</code>, and{" "}
                    <code className="text-xs font-mono bg-muted rounded px-1">{"{appointment_time}"}</code>.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          </>
        )}
      </CardContent>
    </Card>
  );
}
