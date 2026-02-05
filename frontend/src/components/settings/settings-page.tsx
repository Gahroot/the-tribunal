"use client";

import { User, Bell, Webhook, CreditCard, Building2, Tags } from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ProfileSettingsTab } from "@/components/settings/profile-settings-tab";
import { NotificationsSettingsTab } from "@/components/settings/notifications-settings-tab";
import { IntegrationsSettingsTab } from "@/components/settings/integrations-settings-tab";
import { BillingSettingsTab } from "@/components/settings/billing-settings-tab";
import { TeamSettingsTab } from "@/components/settings/team-settings-tab";
import { TagManagement } from "@/components/tags/tag-management";

const settingsTabs = [
  { value: "profile", label: "Profile", icon: User },
  { value: "tags", label: "Tags", icon: Tags },
  { value: "notifications", label: "Notifications", icon: Bell },
  { value: "integrations", label: "Integrations", icon: Webhook },
  { value: "billing", label: "Billing", icon: CreditCard },
  { value: "team", label: "Team", icon: Building2 },
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
        <TabsList className="grid w-full grid-cols-6 lg:w-auto lg:inline-grid">
          {settingsTabs.map((tab) => (
            <TabsTrigger key={tab.value} value={tab.value} className="gap-2">
              <tab.icon className="size-4" />
              <span className="hidden sm:inline">{tab.label}</span>
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="profile">
          <ProfileSettingsTab />
        </TabsContent>

        <TabsContent value="tags">
          <TagManagement />
        </TabsContent>

        <TabsContent value="notifications">
          <NotificationsSettingsTab />
        </TabsContent>

        <TabsContent value="integrations">
          <IntegrationsSettingsTab />
        </TabsContent>

        <TabsContent value="billing">
          <BillingSettingsTab />
        </TabsContent>

        <TabsContent value="team">
          <TeamSettingsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
