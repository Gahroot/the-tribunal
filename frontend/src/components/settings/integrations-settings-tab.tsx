"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Phone, Mail, Calendar, Webhook, Key, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PhoneNumbersSection } from "@/components/settings/phone-numbers-section";
import { IntegrationConfigDialog } from "@/components/settings/integration-config-dialog";
import { useWorkspaceId } from "@/hooks/use-workspace-id";
import { settingsApi } from "@/lib/api/settings";
import {
  integrationsApi,
  type IntegrationWithMaskedCredentials,
} from "@/lib/api/integrations";

type IntegrationType = "calcom" | "telnyx" | "openai" | "sendgrid";

function getIntegrationIcon(type: string) {
  switch (type) {
    case "calcom":
      return Calendar;
    case "telnyx":
      return Phone;
    case "sendgrid":
      return Mail;
    default:
      return Webhook;
  }
}

function getIntegrationColor(type: string) {
  switch (type) {
    case "calcom":
      return "text-primary bg-primary/10";
    case "telnyx":
      return "text-red-500 bg-red-500/10";
    case "sendgrid":
      return "text-blue-500 bg-blue-500/10";
    default:
      return "text-purple-500 bg-purple-500/10";
  }
}

export function IntegrationsSettingsTab() {
  const workspaceId = useWorkspaceId();
  const [integrationDialogOpen, setIntegrationDialogOpen] = useState(false);
  const [selectedIntegration, setSelectedIntegration] =
    useState<IntegrationType | null>(null);

  // Fetch integrations (status display)
  const { data: integrationsData, isLoading: integrationsLoading } = useQuery({
    queryKey: ["settings", "integrations", workspaceId],
    queryFn: () => settingsApi.getIntegrations(workspaceId!),
    enabled: !!workspaceId,
  });

  // Fetch configured integrations (with credentials)
  const { data: configuredIntegrations } = useQuery({
    queryKey: ["integrations", workspaceId],
    queryFn: () => integrationsApi.list(workspaceId!),
    enabled: !!workspaceId,
  });

  // Helper to find existing integration by type
  const getExistingIntegration = (
    type: IntegrationType
  ): IntegrationWithMaskedCredentials | null => {
    return (
      configuredIntegrations?.find((i) => i.integration_type === type) ?? null
    );
  };

  // Handler to open integration config dialog
  const handleConfigureIntegration = (type: IntegrationType) => {
    setSelectedIntegration(type);
    setIntegrationDialogOpen(true);
  };

  return (
    <div className="space-y-6">
      {/* Phone Numbers Section */}
      <PhoneNumbersSection />

      <div className="grid gap-4 md:grid-cols-2">
        {integrationsLoading ? (
          <div className="col-span-2 flex items-center justify-center py-12">
            <Loader2 className="size-6 animate-spin text-muted-foreground" />
          </div>
        ) : (
          integrationsData?.integrations.map((integration) => {
            const Icon = getIntegrationIcon(integration.integration_type);
            const colorClass = getIntegrationColor(integration.integration_type);

            return (
              <Card key={integration.integration_type}>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div
                        className={`flex size-10 items-center justify-center rounded-lg ${colorClass}`}
                      >
                        <Icon className="size-5" />
                      </div>
                      <div>
                        <CardTitle className="text-base">
                          {integration.display_name}
                        </CardTitle>
                        <CardDescription>
                          {integration.description}
                        </CardDescription>
                      </div>
                    </div>
                    {integration.is_connected ? (
                      <Badge className="bg-green-500/10 text-green-500 border-green-500/20">
                        Connected
                      </Badge>
                    ) : (
                      <Badge variant="outline">Not Connected</Badge>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    {integration.is_connected
                      ? `${integration.display_name} is connected and ready to use.`
                      : `Connect ${integration.display_name} to enable this integration.`}
                  </p>
                </CardContent>
                <CardFooter>
                  {integration.is_connected ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        handleConfigureIntegration(
                          integration.integration_type as IntegrationType
                        )
                      }
                    >
                      Configure
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      onClick={() =>
                        handleConfigureIntegration(
                          integration.integration_type as IntegrationType
                        )
                      }
                    >
                      Connect
                    </Button>
                  )}
                </CardFooter>
              </Card>
            );
          })
        )}
      </div>

      {/* API Keys */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Key className="size-5" />
            API Keys
          </CardTitle>
          <CardDescription>
            Manage API keys for programmatic access
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between p-3 rounded-lg border">
            <div>
              <p className="font-medium">Production Key</p>
              <p className="text-sm text-muted-foreground font-mono">
                sk_live_****************************1234
              </p>
            </div>
            <Button variant="outline" size="sm">
              Reveal
            </Button>
          </div>
          <div className="flex items-center justify-between p-3 rounded-lg border">
            <div>
              <p className="font-medium">Test Key</p>
              <p className="text-sm text-muted-foreground font-mono">
                sk_test_****************************5678
              </p>
            </div>
            <Button variant="outline" size="sm">
              Reveal
            </Button>
          </div>
        </CardContent>
        <CardFooter>
          <Button variant="outline">Generate New Key</Button>
        </CardFooter>
      </Card>

      {/* Integration Config Dialog */}
      {selectedIntegration && (
        <IntegrationConfigDialog
          open={integrationDialogOpen}
          onOpenChange={setIntegrationDialogOpen}
          integrationType={selectedIntegration}
          existingIntegration={getExistingIntegration(selectedIntegration)}
        />
      )}
    </div>
  );
}
