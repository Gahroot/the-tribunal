"use client";

import type { UseFormReturn } from "react-hook-form";
import type { AgentFormValues } from "./create-agent-form";

import { ChevronDown, Globe, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { FormField } from "@/components/ui/form";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { GROK_BUILTIN_TOOLS } from "@/lib/voice-constants";
import { INTEGRATIONS_WITH_TOOLS, getRiskLevelBadge } from "./agent-form-utils";

interface ToolsIntegrationsStepProps {
  form: UseFormReturn<AgentFormValues>;
  pricingTier: string;
  enabledToolIds: Record<string, string[]>;
}

export function ToolsIntegrationsStep({
  form,
  pricingTier,
  enabledToolIds,
}: ToolsIntegrationsStepProps) {
  return (
    <Card>
      <CardContent className="space-y-4 p-6">
        <div className="mb-2">
          <h2 className="text-lg font-medium">Tools & Integrations</h2>
          <p className="text-sm text-muted-foreground">
            Enable integrations and select which tools your agent can access. High-risk
            tools are disabled by default for security.
          </p>
        </div>

        <div className="space-y-3">
          {INTEGRATIONS_WITH_TOOLS.map((integration) => (
            <FormField
              key={integration.id}
              control={form.control}
              name="enabledTools"
              render={({ field }) => {
                const isEnabled = field.value?.includes(integration.id);
                return (
                  <Collapsible>
                    <div className="rounded-lg border">
                      <div className="flex items-center justify-between p-4">
                        <div className="flex items-center space-x-3">
                          <Checkbox
                            checked={isEnabled}
                            onCheckedChange={(checked) => {
                              const current = field.value ?? [];
                              if (checked) {
                                field.onChange([...current, integration.id]);
                                // Auto-enable default tools
                                const defaultTools =
                                  integration.tools
                                    ?.filter((t) => t.defaultEnabled)
                                    .map((t) => t.id) ?? [];
                                if (defaultTools.length > 0) {
                                  const currentToolIds = form.getValues("enabledToolIds") ?? {};
                                  form.setValue("enabledToolIds", {
                                    ...currentToolIds,
                                    [integration.id]: defaultTools,
                                  });
                                }
                              } else {
                                field.onChange(current.filter((v) => v !== integration.id));
                                // Clear tool selection
                                const currentToolIds = form.getValues("enabledToolIds") ?? {};
                                // eslint-disable-next-line @typescript-eslint/no-unused-vars
                                const { [integration.id]: _removed, ...rest } = currentToolIds;
                                form.setValue("enabledToolIds", rest);
                              }
                            }}
                          />
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-medium">{integration.name}</span>
                              {integration.isBuiltIn && (
                                <Badge variant="secondary" className="text-xs">
                                  Built-in
                                </Badge>
                              )}
                            </div>
                            <p className="text-sm text-muted-foreground">
                              {integration.description}
                            </p>
                          </div>
                        </div>
                        {isEnabled && integration.tools && integration.tools.length > 0 && (
                          <CollapsibleTrigger asChild>
                            <Button type="button" variant="ghost" size="sm">
                              <ChevronDown className="h-4 w-4" />
                              <span className="ml-1">
                                {enabledToolIds?.[integration.id]?.length ?? 0} /{" "}
                                {integration.tools.length} tools
                              </span>
                            </Button>
                          </CollapsibleTrigger>
                        )}
                      </div>

                      {isEnabled && integration.tools && integration.tools.length > 0 && (
                        <CollapsibleContent>
                          <div className="border-t bg-muted/30 p-4">
                            <div className="mb-3 flex items-center justify-between">
                              <span className="text-sm font-medium">Available Tools</span>
                              <div className="flex gap-2">
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  onClick={() => {
                                    const allToolIds = integration.tools?.map((t) => t.id) ?? [];
                                    const currentToolIds = form.getValues("enabledToolIds") ?? {};
                                    form.setValue("enabledToolIds", {
                                      ...currentToolIds,
                                      [integration.id]: allToolIds,
                                    });
                                  }}
                                >
                                  Select All
                                </Button>
                                <Button
                                  type="button"
                                  variant="outline"
                                  size="sm"
                                  onClick={() => {
                                    const currentToolIds = form.getValues("enabledToolIds") ?? {};
                                    form.setValue("enabledToolIds", {
                                      ...currentToolIds,
                                      [integration.id]: [],
                                    });
                                  }}
                                >
                                  Clear All
                                </Button>
                              </div>
                            </div>
                            <div className="space-y-2">
                              {integration.tools.map((tool) => {
                                const riskBadge = getRiskLevelBadge(tool.riskLevel);
                                const RiskIcon = riskBadge.icon;
                                const currentTools = enabledToolIds?.[integration.id] ?? [];
                                const isToolEnabled = currentTools.includes(tool.id);
                                return (
                                  <div
                                    key={tool.id}
                                    className="flex items-center justify-between rounded-md border bg-background p-3"
                                  >
                                    <div className="flex items-center space-x-3">
                                      <Checkbox
                                        checked={isToolEnabled}
                                        onCheckedChange={(checked) => {
                                          const allToolIds = form.getValues("enabledToolIds") ?? {};
                                          const toolsForIntegration = allToolIds[integration.id] ?? [];
                                          const newTools = checked
                                            ? [...toolsForIntegration, tool.id]
                                            : toolsForIntegration.filter((t) => t !== tool.id);
                                          form.setValue("enabledToolIds", {
                                            ...allToolIds,
                                            [integration.id]: newTools,
                                          });
                                        }}
                                      />
                                      <div>
                                        <span className="text-sm font-medium">{tool.name}</span>
                                        <p className="text-xs text-muted-foreground">
                                          {tool.description}
                                        </p>
                                      </div>
                                    </div>
                                    <Badge variant={riskBadge.variant} className={riskBadge.color}>
                                      <RiskIcon className="mr-1 h-3 w-3" />
                                      {tool.riskLevel}
                                    </Badge>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        </CollapsibleContent>
                      )}
                    </div>
                  </Collapsible>
                );
              }}
            />
          ))}
        </div>

        {/* Grok-specific built-in tools */}
        {pricingTier === "grok" && (
          <div className="mt-6 rounded-lg border bg-muted/30 p-4">
            <h3 className="mb-2 text-sm font-medium">
              Grok Built-in Search Tools
            </h3>
            <p className="mb-4 text-sm text-muted-foreground">
              Grok has built-in search capabilities that execute automatically during
              conversations. Enable the ones you want your agent to use.
            </p>
            <FormField
              control={form.control}
              name="enabledTools"
              render={({ field }) => (
                <div className="space-y-3">
                  {GROK_BUILTIN_TOOLS.map((tool) => {
                    const isEnabled = field.value?.includes(tool.id);
                    const Icon = tool.id === "web_search" ? Globe : Search;
                    return (
                      <div
                        key={tool.id}
                        className={cn(
                          "flex items-start gap-3 rounded-lg border bg-background p-4 transition-colors",
                          isEnabled && "border-primary bg-primary/5"
                        )}
                      >
                        <Checkbox
                          checked={isEnabled}
                          onCheckedChange={(checked) => {
                            const current = field.value ?? [];
                            if (checked) {
                              field.onChange([...current, tool.id]);
                            } else {
                              field.onChange(current.filter((v) => v !== tool.id));
                            }
                          }}
                        />
                        <div className="flex-1 space-y-1">
                          <div className="flex items-center gap-2">
                            <Icon className="h-4 w-4 text-muted-foreground" />
                            <span className="font-medium">{tool.name}</span>
                            <Badge variant="secondary" className="text-xs">
                              Auto
                            </Badge>
                          </div>
                          <p className="text-sm text-muted-foreground">
                            {tool.description}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
