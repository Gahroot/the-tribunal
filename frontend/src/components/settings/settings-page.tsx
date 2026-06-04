"use client";

import { User, Bell, Webhook, CreditCard, Building2, Tags, FileInput, HandHeart } from "lucide-react";

import { BillingSettingsTab } from "@/components/settings/billing-settings-tab";
import { IntegrationsSettingsTab } from "@/components/settings/integrations-settings-tab";
import { LeadSourcesSettingsTab } from "@/components/settings/lead-sources-settings-tab";
import { NotificationsSettingsTab } from "@/components/settings/notifications-settings-tab";
import { NudgeSettingsTab } from "@/components/settings/nudge-settings-tab";
import { ProfileSettingsTab } from "@/components/settings/profile-settings-tab";
import { TeamSettingsTab } from "@/components/settings/team-settings-tab";
import { TagManagement } from "@/components/tags/tag-management";
import { QueryErrorBoundary } from "@/components/ui/query-error-boundary";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const settingsTabs = [
  { value: "profile", label: "Profile", icon: User },
  { value: "tags", label: "Tags", icon: Tags },
  { value: "notifications", label: "Notifications", icon: Bell },
  { value: "nudges", label: "Nudges", icon: HandHeart },
  { value: "integrations", label: "Integrations", icon: Webhook },
  { value: "billing", label: "Billing", icon: CreditCard },
  { value: "team", label: "Team", icon: Building2 },
  { value: "lead-sources", label: "Lead Sources", icon: FileInput },
];

export function SettingsPage() {
  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">
          Manage your account and application preferences
        </p>
      </div>

      <Tabs defaultValue="profile" className="space-y-6">
        <TabsList className="grid w-full grid-cols-8 lg:w-auto lg:inline-grid">
          {settingsTabs.map((tab) => (
            <TabsTrigger key={tab.value} value={tab.value} className="gap-2">
              <tab.icon className="size-4" />
              <span className="hidden sm:inline">{tab.label}</span>
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="profile">
          <QueryErrorBoundary message="Failed to load profile settings. Please try again.">
            <ProfileSettingsTab />
          </QueryErrorBoundary>
        </TabsContent>

        <TabsContent value="tags">
          <QueryErrorBoundary message="Failed to load tags. Please try again.">
            <TagManagement />
          </QueryErrorBoundary>
        </TabsContent>

        <TabsContent value="notifications">
          <QueryErrorBoundary message="Failed to load notification settings. Please try again.">
            <NotificationsSettingsTab />
          </QueryErrorBoundary>
        </TabsContent>

        <TabsContent value="nudges">
          <QueryErrorBoundary message="Failed to load nudge settings. Please try again.">
            <NudgeSettingsTab />
          </QueryErrorBoundary>
        </TabsContent>

        <TabsContent value="integrations">
          <QueryErrorBoundary message="Failed to load integrations. Please try again.">
            <IntegrationsSettingsTab />
          </QueryErrorBoundary>
        </TabsContent>

        <TabsContent value="billing">
          <QueryErrorBoundary message="Failed to load billing settings. Please try again.">
            <BillingSettingsTab />
          </QueryErrorBoundary>
        </TabsContent>

        <TabsContent value="team">
          <QueryErrorBoundary message="Failed to load team settings. Please try again.">
            <TeamSettingsTab />
          </QueryErrorBoundary>
        </TabsContent>

        <TabsContent value="lead-sources">
          <QueryErrorBoundary message="Failed to load lead sources. Please try again.">
            <LeadSourcesSettingsTab />
          </QueryErrorBoundary>
        </TabsContent>
      </Tabs>
    </div>
  );
}
