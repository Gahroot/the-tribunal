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
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Slider } from "@/components/ui/slider";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronDown, Phone } from "lucide-react";
import type { AgentResponse } from "@/lib/api/agents";
import type { EditAgentFormValues } from "@/components/agents/agent-edit-schema";
import { ReminderOffsetsInput } from "@/components/agents/reminder-offsets-input";

interface AdvancedTabProps {
  form: UseFormReturn<EditAgentFormValues>;
  voiceProvider: string;
  agent: AgentResponse;
}

const DEFAULT_REMINDER_TEMPLATE_PLACEHOLDER =
  "Hi {first_name}, this is a reminder about your appointment on {appointment_date} at {appointment_time}. Reply STOP to opt out.";

const REMINDER_VARIABLES = [
  { name: "{first_name}", description: "Contact's first name" },
  { name: "{last_name}", description: "Contact's last name" },
  { name: "{appointment_date}", description: "Date of the appointment (e.g. March 22, 2026)" },
  { name: "{appointment_time}", description: "Time of the appointment (e.g. 2:30 PM)" },
  { name: "{reschedule_link}", description: "Link for the contact to reschedule" },
];

export function AdvancedTab({ form, voiceProvider, agent }: AdvancedTabProps) {
  const reminderEnabled = form.watch("reminderEnabled");
  const reminderTemplate = form.watch("reminderTemplate") ?? "";
  const charCount = (reminderTemplate ?? "").length;

  return (
    <>
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

      {/* Appointment Reminders */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">Appointment Reminders</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <FormField
            control={form.control}
            name="reminderEnabled"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                <div className="space-y-0.5">
                  <FormLabel className="text-base">Enable Reminders</FormLabel>
                  <FormDescription>
                    Automatically send SMS reminders before appointments
                  </FormDescription>
                </div>
                <FormControl>
                  <Switch checked={field.value} onCheckedChange={field.onChange} />
                </FormControl>
              </FormItem>
            )}
          />

          {reminderEnabled && (
            <>
              {/* Multi-touch reminder offsets */}
              <FormField
                control={form.control}
                name="reminderOffsets"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Reminder Times</FormLabel>
                    <FormControl>
                      <ReminderOffsetsInput
                        value={field.value}
                        onChange={field.onChange}
                      />
                    </FormControl>
                    <FormDescription>
                      Send reminders at each of these times before the appointment.
                    </FormDescription>
                    {field.value.length === 0 && (
                      <p className="text-xs text-amber-600">
                        Add at least one reminder time for reminders to be sent.
                      </p>
                    )}
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Custom SMS template */}
              <FormField
                control={form.control}
                name="reminderTemplate"
                render={({ field }) => (
                  <FormItem>
                    <div className="flex items-center justify-between">
                      <FormLabel>Custom SMS Template</FormLabel>
                      <span
                        className={`text-xs ${charCount > 160 ? "text-amber-600 font-medium" : "text-muted-foreground"}`}
                      >
                        {charCount} / 160
                        {charCount > 160 ? ` (${Math.ceil(charCount / 153)} segments)` : ""}
                      </span>
                    </div>
                    <FormControl>
                      <Textarea
                        placeholder={DEFAULT_REMINDER_TEMPLATE_PLACEHOLDER}
                        className="min-h-[90px] font-mono text-sm resize-none"
                        value={field.value ?? ""}
                        onChange={(e) => field.onChange(e.target.value || null)}
                      />
                    </FormControl>
                    <FormDescription>
                      Leave blank to use the default message shown in the placeholder above.
                    </FormDescription>
                    <FormMessage />

                    {/* Available variables */}
                    <div className="rounded-md border bg-muted/30 p-3 space-y-1.5">
                      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                        Available variables
                      </p>
                      <div className="grid gap-1">
                        {REMINDER_VARIABLES.map((v) => (
                          <div key={v.name} className="flex items-baseline gap-2">
                            <code className="text-xs font-mono bg-background border rounded px-1 py-0.5 text-foreground shrink-0">
                              {v.name}
                            </code>
                            <span className="text-xs text-muted-foreground">{v.description}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </FormItem>
                )}
              />
            </>
          )}
        </CardContent>
      </Card>

      {/* Experiment Auto-Evaluation */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">Experiment Auto-Evaluation</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <FormField
            control={form.control}
            name="autoEvaluate"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                <div className="space-y-0.5">
                  <FormLabel className="text-base">Auto-Evaluate Experiments</FormLabel>
                  <FormDescription>
                    Automatically declare winners and eliminate underperformers when statistical confidence is reached (95% threshold)
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

      {/* IVR Navigation Settings - Grok only */}
      {voiceProvider === "grok" && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium">IVR Navigation Settings</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Configure how your agent navigates automated phone menus (IVR systems)
            </p>

            <FormField
              control={form.control}
              name="enableIvrNavigation"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                  <div className="space-y-0.5">
                    <FormLabel className="text-base">Enable IVR Navigation</FormLabel>
                    <FormDescription>
                      Allow agent to detect and navigate through phone menus using DTMF tones
                    </FormDescription>
                  </div>
                  <FormControl>
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  </FormControl>
                </FormItem>
              )}
            />

            {form.watch("enableIvrNavigation") && (
              <>
                <FormField
                  control={form.control}
                  name="ivrNavigationGoal"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Navigation Goal</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="e.g., Reach sales department, Speak to a human representative"
                          {...field}
                        />
                      </FormControl>
                      <FormDescription>
                        What should the agent try to achieve when navigating IVR menus?
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <Collapsible>
                  <CollapsibleTrigger asChild>
                    <Button type="button" variant="outline" size="sm" className="w-full justify-between">
                      <span className="flex items-center gap-2">
                        <Phone className="h-4 w-4" />
                        Advanced IVR Timing
                      </span>
                      <ChevronDown className="h-4 w-4" />
                    </Button>
                  </CollapsibleTrigger>
                  <CollapsibleContent className="space-y-4 pt-4">
                    <FormField
                      control={form.control}
                      name="ivrSilenceDurationMs"
                      render={({ field }) => (
                        <FormItem>
                          <div className="flex items-center justify-between">
                            <FormLabel>Silence Duration</FormLabel>
                            <span className="text-sm font-medium">{field.value}ms</span>
                          </div>
                          <FormControl>
                            <Slider
                              min={1000}
                              max={10000}
                              step={500}
                              value={[field.value]}
                              onValueChange={(value) => field.onChange(value[0])}
                              className="w-full"
                            />
                          </FormControl>
                          <FormDescription>
                            How long to wait for menu to complete before responding
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="ivrPostDtmfCooldownMs"
                      render={({ field }) => (
                        <FormItem>
                          <div className="flex items-center justify-between">
                            <FormLabel>Post-DTMF Cooldown</FormLabel>
                            <span className="text-sm font-medium">{field.value}ms</span>
                          </div>
                          <FormControl>
                            <Slider
                              min={0}
                              max={10000}
                              step={500}
                              value={[field.value]}
                              onValueChange={(value) => field.onChange(value[0])}
                              className="w-full"
                            />
                          </FormControl>
                          <FormDescription>
                            Minimum wait time after pressing a button before pressing another
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="ivrLoopThreshold"
                      render={({ field }) => (
                        <FormItem>
                          <div className="flex items-center justify-between">
                            <FormLabel>Loop Detection Threshold</FormLabel>
                            <span className="text-sm font-medium">{field.value} repeats</span>
                          </div>
                          <FormControl>
                            <Slider
                              min={1}
                              max={10}
                              step={1}
                              value={[field.value]}
                              onValueChange={(value) => field.onChange(value[0])}
                              className="w-full"
                            />
                          </FormControl>
                          <FormDescription>
                            Number of menu repeats before trying alternative options
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </CollapsibleContent>
                </Collapsible>
              </>
            )}
          </CardContent>
        </Card>
      )}

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
    </>
  );
}
