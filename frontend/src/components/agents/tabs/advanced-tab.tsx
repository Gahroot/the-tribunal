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

interface AdvancedTabProps {
  form: UseFormReturn<EditAgentFormValues>;
  voiceProvider: string;
  agent: AgentResponse;
}

export function AdvancedTab({ form, voiceProvider, agent }: AdvancedTabProps) {
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
        <CardContent className="space-y-3">
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

          {form.watch("reminderEnabled") && (
            <FormField
              control={form.control}
              name="reminderMinutesBefore"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Minutes Before Appointment</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      min={5}
                      max={1440}
                      value={field.value}
                      onChange={(e) => field.onChange(parseInt(e.target.value) || 30)}
                    />
                  </FormControl>
                  <FormDescription>
                    How many minutes before the appointment to send the reminder (5-1440)
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />
          )}
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
