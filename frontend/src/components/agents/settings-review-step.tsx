"use client";

import type { UseFormReturn } from "react-hook-form";
import type { AgentFormValues } from "./create-agent-form";
import type { PRICING_TIERS } from "@/lib/pricing-tiers";

import { Phone, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
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
import { Badge } from "@/components/ui/badge";

interface SettingsReviewStepProps {
  form: UseFormReturn<AgentFormValues>;
  pricingTier: string;
  agentName: string;
  systemPrompt: string;
  enabledTools: string[];
  selectedTier: (typeof PRICING_TIERS)[number] | undefined;
}

export function SettingsReviewStep({
  form,
  pricingTier,
  agentName,
  systemPrompt,
  enabledTools,
  selectedTier,
}: SettingsReviewStepProps) {
  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-4 p-6">
          <div className="mb-2">
            <h2 className="text-lg font-medium">Call Settings</h2>
            <p className="text-sm text-muted-foreground">
              Configure recording and transcription
            </p>
          </div>

          <FormField
            control={form.control}
            name="enableRecording"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                <div className="space-y-0.5">
                  <FormLabel className="text-sm font-medium">Call Recording</FormLabel>
                  <FormDescription className="text-xs">
                    Record all calls for quality assurance
                  </FormDescription>
                </div>
                <FormControl>
                  <Switch checked={field.value} onCheckedChange={field.onChange} />
                </FormControl>
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="enableTranscript"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                <div className="space-y-0.5">
                  <FormLabel className="text-sm font-medium">Transcripts</FormLabel>
                  <FormDescription className="text-xs">
                    Save searchable conversation transcripts
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

      <Card>
        <CardContent className="space-y-4 p-6">
          <div className="mb-2">
            <h2 className="text-lg font-medium">AI Settings</h2>
            <p className="text-sm text-muted-foreground">
              Fine-tune the AI response behavior
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
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
                        {field.value?.toFixed(1) ?? "0.7"} ({getTemperatureLabel(field.value ?? 0.7)})
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
                    <FormMessage />
                  </FormItem>
                );
              }}
            />

            <FormField
              control={form.control}
              name="maxTokens"
              render={({ field }) => (
                <FormItem>
                  <div className="flex items-center justify-between">
                    <FormLabel>Max Tokens</FormLabel>
                    <span className="text-sm font-medium">
                      {(field.value ?? 2000).toLocaleString()}
                    </span>
                  </div>
                  <FormControl>
                    <div className="space-y-2">
                      <Slider
                        min={100}
                        max={4000}
                        step={100}
                        value={[field.value ?? 2000]}
                        onValueChange={(value) => field.onChange(value[0])}
                        className="w-full"
                      />
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span>100</span>
                        <span>4,000</span>
                      </div>
                    </div>
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </div>
        </CardContent>
      </Card>

      {/* IVR Navigation Settings - Grok only */}
      {pricingTier === "grok" && (
        <Card>
          <CardContent className="space-y-4 p-6">
            <div className="mb-2">
              <h2 className="text-lg font-medium">IVR Navigation Settings</h2>
              <p className="text-sm text-muted-foreground">
                Configure how your agent navigates automated phone menus (IVR systems)
              </p>
            </div>

            <FormField
              control={form.control}
              name="enableIvrNavigation"
              render={({ field }) => (
                <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                  <div className="space-y-0.5">
                    <FormLabel className="text-sm font-medium">Enable IVR Navigation</FormLabel>
                    <FormDescription className="text-xs">
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
                        Advanced IVR Settings
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
                            How long to wait for menu to complete before responding (default: 3000ms)
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
                            Minimum wait time after pressing a button before pressing another (default: 3000ms)
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
                            Number of menu repeats before trying alternative options (default: 2)
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

      {/* Appointment Reminders */}
      <Card>
        <CardContent className="space-y-4 p-6">
          <div className="mb-2">
            <h2 className="text-lg font-medium">Appointment Reminders</h2>
            <p className="text-sm text-muted-foreground">
              Send SMS reminders before scheduled appointments
            </p>
          </div>

          <FormField
            control={form.control}
            name="reminderEnabled"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                <div className="space-y-0.5">
                  <FormLabel className="text-sm font-medium">Enable Reminders</FormLabel>
                  <FormDescription className="text-xs">
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

      {/* Experiment Auto-Evaluation */}
      <Card>
        <CardContent className="space-y-4 p-6">
          <div className="mb-2">
            <h2 className="text-lg font-medium">Experiment Auto-Evaluation</h2>
            <p className="text-sm text-muted-foreground">
              Automatically manage A/B test outcomes
            </p>
          </div>

          <FormField
            control={form.control}
            name="autoEvaluate"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center justify-between rounded-lg border p-3">
                <div className="space-y-0.5">
                  <FormLabel className="text-sm font-medium">Auto-Evaluate Experiments</FormLabel>
                  <FormDescription className="text-xs">
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

      {/* Summary Card */}
      <Card className="border-primary/30 bg-primary/5">
        <CardContent className="p-6">
          <h2 className="mb-4 text-lg font-medium">Review Your Agent</h2>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-3">
              <div>
                <p className="text-xs text-muted-foreground">Name</p>
                <p className="font-medium">{agentName || "Not set"}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Pricing Tier</p>
                <div className="flex items-center gap-2">
                  <span className="font-medium">{selectedTier?.name}</span>
                  <Badge variant="outline" className="text-[10px]">
                    ${selectedTier?.costPerHour.toFixed(2)}/hr
                  </Badge>
                </div>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">AI Model</p>
                <p className="font-mono text-sm">{selectedTier?.config.llmModel}</p>
              </div>
            </div>

            <div className="space-y-3">
              <div>
                <p className="text-xs text-muted-foreground">System Prompt</p>
                <p className="text-sm">
                  {systemPrompt
                    ? `${systemPrompt.slice(0, 80)}${systemPrompt.length > 80 ? "..." : ""}`
                    : "Not set"}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Tools Enabled</p>
                <p className="font-medium">
                  {enabledTools.length > 0
                    ? `${enabledTools.length} integration${enabledTools.length > 1 ? "s" : ""}`
                    : "None"}
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
