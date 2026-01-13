"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  User,
  Bell,
  Phone,
  Mail,
  Calendar,
  Webhook,
  Key,
  CreditCard,
  Building2,
  Save,
  Check,
  Loader2,
  Trash2,
  UserPlus,
  Clock,
  X,
} from "lucide-react";

import { toast } from "sonner";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { PhoneNumbersSection } from "@/components/settings/phone-numbers-section";
import { IntegrationConfigDialog } from "@/components/settings/integration-config-dialog";
import { useWorkspaceId } from "@/hooks/use-workspace-id";
import { useWorkspace } from "@/providers/workspace-provider";
import {
  settingsApi,
  type NotificationSettings,
} from "@/lib/api/settings";
import { workspacesApi } from "@/lib/api/workspaces";
import {
  integrationsApi,
  type IntegrationWithMaskedCredentials,
} from "@/lib/api/integrations";
import { invitationsApi } from "@/lib/api/invitations";
import { InviteMemberDialog } from "@/components/workspaces/invite-member-dialog";
import { EditMemberDialog } from "@/components/workspaces/edit-member-dialog";
import { type TeamMember } from "@/lib/api/settings";

type IntegrationType = "calcom" | "telnyx" | "openai" | "sendgrid";

const settingsTabs = [
  { value: "profile", label: "Profile", icon: User },
  { value: "notifications", label: "Notifications", icon: Bell },
  { value: "integrations", label: "Integrations", icon: Webhook },
  { value: "billing", label: "Billing", icon: CreditCard },
  { value: "team", label: "Team", icon: Building2 },
];

const TIMEZONES = [
  { value: "America/New_York", label: "America/New York (EST)" },
  { value: "America/Chicago", label: "America/Chicago (CST)" },
  { value: "America/Denver", label: "America/Denver (MST)" },
  { value: "America/Los_Angeles", label: "America/Los Angeles (PST)" },
  { value: "Europe/London", label: "Europe/London (GMT)" },
  { value: "Europe/Paris", label: "Europe/Paris (CET)" },
  { value: "Asia/Tokyo", label: "Asia/Tokyo (JST)" },
  { value: "Australia/Sydney", label: "Australia/Sydney (AEST)" },
];

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

function getInitials(name: string | null, email: string): string {
  if (name) {
    const parts = name.split(" ");
    if (parts.length >= 2) {
      return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
  }
  return email.slice(0, 2).toUpperCase();
}

export function SettingsPage() {
  const workspaceId = useWorkspaceId();
  const { currentWorkspace, workspaces, setCurrentWorkspace } = useWorkspace();
  const queryClient = useQueryClient();
  const router = useRouter();

  const [profileSaved, setProfileSaved] = useState(false);
  const [workspaceSaved, setWorkspaceSaved] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [integrationDialogOpen, setIntegrationDialogOpen] = useState(false);
  const [selectedIntegration, setSelectedIntegration] = useState<IntegrationType | null>(null);
  const [inviteDialogOpen, setInviteDialogOpen] = useState(false);
  const [editMemberDialogOpen, setEditMemberDialogOpen] = useState(false);
  const [selectedMember, setSelectedMember] = useState<TeamMember | null>(null);

  // Track local edits separate from server state
  const [localEdits, setLocalEdits] = useState<{
    full_name?: string;
    phone_number?: string;
    timezone?: string;
  }>({});

  // Track workspace local edits
  const [workspaceEdits, setWorkspaceEdits] = useState<{
    name?: string;
    description?: string;
  }>({});

  // Track company info edits (stored in workspace.settings)
  const [companyEdits, setCompanyEdits] = useState<{
    business_name?: string;
    phone?: string;
    website?: string;
    address?: string;
    city?: string;
    state?: string;
    postal_code?: string;
    country?: string;
    timezone?: string;
  }>({});
  const [companySaved, setCompanySaved] = useState(false);

  // Fetch profile
  const { data: profile, isLoading: profileLoading } = useQuery({
    queryKey: ["settings", "profile"],
    queryFn: settingsApi.getProfile,
  });

  // Fetch notifications
  const { data: notifications, isLoading: notificationsLoading } = useQuery({
    queryKey: ["settings", "notifications"],
    queryFn: settingsApi.getNotifications,
  });

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
    return configuredIntegrations?.find((i) => i.integration_type === type) ?? null;
  };

  // Handler to open integration config dialog
  const handleConfigureIntegration = (type: IntegrationType) => {
    setSelectedIntegration(type);
    setIntegrationDialogOpen(true);
  };

  // Fetch team members
  const { data: teamMembers, isLoading: teamLoading } = useQuery({
    queryKey: ["settings", "team", workspaceId],
    queryFn: () => settingsApi.getTeamMembers(workspaceId!),
    enabled: !!workspaceId,
  });

  // Fetch pending invitations (only for admins/owners)
  const isAdminOrOwner =
    currentWorkspace?.role === "owner" || currentWorkspace?.role === "admin";
  const { data: pendingInvitations, isLoading: invitationsLoading } = useQuery({
    queryKey: ["invitations", workspaceId],
    queryFn: () => invitationsApi.list(workspaceId!),
    enabled: !!workspaceId && isAdminOrOwner,
  });

  // Cancel invitation mutation
  const cancelInvitationMutation = useMutation({
    mutationFn: (invitationId: string) =>
      invitationsApi.cancel(workspaceId!, invitationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["invitations", workspaceId] });
      toast.success("Invitation cancelled");
    },
    onError: () => {
      toast.error("Failed to cancel invitation");
    },
  });

  // Derive form values from profile + local edits
  const profileForm = {
    full_name: localEdits.full_name ?? profile?.full_name ?? "",
    phone_number: localEdits.phone_number ?? profile?.phone_number ?? "",
    timezone: localEdits.timezone ?? profile?.timezone ?? "America/New_York",
  };

  // Profile mutation
  const profileMutation = useMutation({
    mutationFn: settingsApi.updateProfile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings", "profile"] });
      setLocalEdits({}); // Clear local edits after successful save
      setProfileSaved(true);
      setTimeout(() => setProfileSaved(false), 2000);
    },
  });

  // Notifications mutation
  const notificationsMutation = useMutation({
    mutationFn: settingsApi.updateNotifications,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings", "notifications"] });
    },
  });

  // Workspace update mutation
  const workspaceUpdateMutation = useMutation({
    mutationFn: (data: { name?: string; description?: string }) =>
      workspacesApi.update(workspaceId!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      setWorkspaceEdits({});
      setWorkspaceSaved(true);
      toast.success("Workspace updated successfully");
      setTimeout(() => setWorkspaceSaved(false), 2000);
    },
    onError: () => {
      toast.error("Failed to update workspace");
    },
  });

  // Workspace delete mutation
  const workspaceDeleteMutation = useMutation({
    mutationFn: () => workspacesApi.delete(workspaceId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      toast.success("Workspace deleted successfully");
      setDeleteDialogOpen(false);
      // Switch to another workspace if available
      const remainingWorkspaces = workspaces.filter(
        (ws) => ws.workspace.id !== workspaceId
      );
      if (remainingWorkspaces.length > 0) {
        setCurrentWorkspace(remainingWorkspaces[0].workspace.id);
      } else {
        router.push("/");
      }
    },
    onError: () => {
      toast.error("Failed to delete workspace");
    },
  });

  // Set default workspace mutation
  const setDefaultMutation = useMutation({
    mutationFn: () => workspacesApi.setDefault(workspaceId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      toast.success("Default workspace updated");
    },
    onError: () => {
      toast.error("Failed to set default workspace");
    },
  });

  // Derived workspace form values
  const workspaceForm = {
    name: workspaceEdits.name ?? currentWorkspace?.workspace.name ?? "",
    description:
      workspaceEdits.description ?? currentWorkspace?.workspace.description ?? "",
  };

  // Derived company form values (from workspace.settings)
  const workspaceSettings = currentWorkspace?.workspace.settings as Record<string, unknown> | undefined;
  const companyForm = {
    business_name: companyEdits.business_name ?? (workspaceSettings?.business_name as string) ?? "",
    phone: companyEdits.phone ?? (workspaceSettings?.phone as string) ?? "",
    website: companyEdits.website ?? (workspaceSettings?.website as string) ?? "",
    address: companyEdits.address ?? (workspaceSettings?.address as string) ?? "",
    city: companyEdits.city ?? (workspaceSettings?.city as string) ?? "",
    state: companyEdits.state ?? (workspaceSettings?.state as string) ?? "",
    postal_code: companyEdits.postal_code ?? (workspaceSettings?.postal_code as string) ?? "",
    country: companyEdits.country ?? (workspaceSettings?.country as string) ?? "",
    timezone: companyEdits.timezone ?? (workspaceSettings?.timezone as string) ?? "America/New_York",
  };

  const handleSaveWorkspace = () => {
    workspaceUpdateMutation.mutate({
      name: workspaceForm.name || undefined,
      description: workspaceForm.description || undefined,
    });
  };

  // Company info update mutation
  const companyUpdateMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      workspacesApi.update(workspaceId!, {
        settings: {
          ...workspaceSettings,
          ...data,
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      setCompanyEdits({});
      setCompanySaved(true);
      toast.success("Company information updated successfully");
      setTimeout(() => setCompanySaved(false), 2000);
    },
    onError: () => {
      toast.error("Failed to update company information");
    },
  });

  const handleSaveCompany = () => {
    companyUpdateMutation.mutate({
      business_name: companyForm.business_name || undefined,
      phone: companyForm.phone || undefined,
      website: companyForm.website || undefined,
      address: companyForm.address || undefined,
      city: companyForm.city || undefined,
      state: companyForm.state || undefined,
      postal_code: companyForm.postal_code || undefined,
      country: companyForm.country || undefined,
      timezone: companyForm.timezone,
    });
  };

  const handleDeleteWorkspace = () => {
    workspaceDeleteMutation.mutate();
  };

  const canEditWorkspace =
    currentWorkspace?.role === "owner" || currentWorkspace?.role === "admin";
  const canDeleteWorkspace = currentWorkspace?.role === "owner";

  const handleEditMember = (member: TeamMember) => {
    setSelectedMember(member);
    setEditMemberDialogOpen(true);
  };

  const handleSaveProfile = () => {
    profileMutation.mutate({
      full_name: profileForm.full_name || null,
      phone_number: profileForm.phone_number || null,
      timezone: profileForm.timezone,
    });
  };

  const handleNotificationChange = (
    key: keyof NotificationSettings,
    value: boolean
  ) => {
    notificationsMutation.mutate({ [key]: value });
  };

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
        <TabsList className="grid w-full grid-cols-5 lg:w-auto lg:inline-grid">
          {settingsTabs.map((tab) => (
            <TabsTrigger
              key={tab.value}
              value={tab.value}
              className="gap-2"
            >
              <tab.icon className="size-4" />
              <span className="hidden sm:inline">{tab.label}</span>
            </TabsTrigger>
          ))}
        </TabsList>

        {/* Profile Tab */}
        <TabsContent value="profile" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Profile Information</CardTitle>
              <CardDescription>
                Update your personal details and preferences
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {profileLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="size-6 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="fullName">Full Name</Label>
                    <Input
                      id="fullName"
                      value={profileForm.full_name}
                      onChange={(e) =>
                        setLocalEdits((prev) => ({
                          ...prev,
                          full_name: e.target.value,
                        }))
                      }
                      placeholder="Enter your full name"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="email">Email</Label>
                    <Input
                      id="email"
                      type="email"
                      value={profile?.email || ""}
                      disabled
                      className="bg-muted"
                    />
                    <p className="text-xs text-muted-foreground">
                      Email cannot be changed
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="phone">Phone Number</Label>
                    <Input
                      id="phone"
                      type="tel"
                      value={profileForm.phone_number}
                      onChange={(e) =>
                        setLocalEdits((prev) => ({
                          ...prev,
                          phone_number: e.target.value,
                        }))
                      }
                      placeholder="+1 (555) 123-4567"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="timezone">Timezone</Label>
                    <Select
                      value={profileForm.timezone}
                      onValueChange={(value) =>
                        setLocalEdits((prev) => ({ ...prev, timezone: value }))
                      }
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {TIMEZONES.map((tz) => (
                          <SelectItem key={tz.value} value={tz.value}>
                            {tz.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </>
              )}
            </CardContent>
            <CardFooter>
              <Button
                onClick={handleSaveProfile}
                disabled={profileMutation.isPending || profileLoading}
              >
                {profileMutation.isPending ? (
                  <>
                    <Loader2 className="mr-2 size-4 animate-spin" />
                    Saving...
                  </>
                ) : profileSaved ? (
                  <>
                    <Check className="mr-2 size-4" />
                    Saved
                  </>
                ) : (
                  <>
                    <Save className="mr-2 size-4" />
                    Save Changes
                  </>
                )}
              </Button>
            </CardFooter>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Appearance</CardTitle>
              <CardDescription>
                Customize the look and feel of the application
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>Dark Mode</Label>
                  <p className="text-sm text-muted-foreground">
                    Use dark theme across the application
                  </p>
                </div>
                <Switch defaultChecked />
              </div>
              <Separator />
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>Compact Mode</Label>
                  <p className="text-sm text-muted-foreground">
                    Reduce spacing for more content on screen
                  </p>
                </div>
                <Switch />
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Notifications Tab */}
        <TabsContent value="notifications" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Email Notifications</CardTitle>
              <CardDescription>
                Configure which emails you want to receive
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {notificationsLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="size-6 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>Email Notifications</Label>
                    <p className="text-sm text-muted-foreground">
                      Receive email notifications for important events
                    </p>
                  </div>
                  <Switch
                    checked={notifications?.notification_email ?? true}
                    onCheckedChange={(checked) =>
                      handleNotificationChange("notification_email", checked)
                    }
                    disabled={notificationsMutation.isPending}
                  />
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>SMS Notifications</CardTitle>
              <CardDescription>
                Receive text message alerts
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {notificationsLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="size-6 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>SMS Notifications</Label>
                    <p className="text-sm text-muted-foreground">
                      Get SMS alerts for critical events
                    </p>
                  </div>
                  <Switch
                    checked={notifications?.notification_sms ?? true}
                    onCheckedChange={(checked) =>
                      handleNotificationChange("notification_sms", checked)
                    }
                    disabled={notificationsMutation.isPending}
                  />
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Push Notifications</CardTitle>
              <CardDescription>
                Real-time alerts in your browser
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {notificationsLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="size-6 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>Push Notifications</Label>
                    <p className="text-sm text-muted-foreground">
                      Receive push notifications in your browser
                    </p>
                  </div>
                  <Switch
                    checked={notifications?.notification_push ?? true}
                    onCheckedChange={(checked) =>
                      handleNotificationChange("notification_push", checked)
                    }
                    disabled={notificationsMutation.isPending}
                  />
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Integrations Tab */}
        <TabsContent value="integrations" className="space-y-6">
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
        </TabsContent>

        {/* Billing Tab - Keep hardcoded for now (requires Stripe integration) */}
        <TabsContent value="billing" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Current Plan</CardTitle>
              <CardDescription>
                You are currently on the Pro plan
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between p-4 rounded-lg border bg-primary/5">
                <div>
                  <h3 className="text-lg font-semibold">Pro Plan</h3>
                  <p className="text-sm text-muted-foreground">
                    $99/month, billed monthly
                  </p>
                </div>
                <Badge>Current Plan</Badge>
              </div>
              <div className="mt-4 grid grid-cols-3 gap-4 text-center">
                <div className="p-3 rounded-lg border">
                  <p className="text-2xl font-bold">5,000</p>
                  <p className="text-sm text-muted-foreground">SMS/month</p>
                </div>
                <div className="p-3 rounded-lg border">
                  <p className="text-2xl font-bold">500</p>
                  <p className="text-sm text-muted-foreground">AI minutes</p>
                </div>
                <div className="p-3 rounded-lg border">
                  <p className="text-2xl font-bold">10</p>
                  <p className="text-sm text-muted-foreground">Team members</p>
                </div>
              </div>
            </CardContent>
            <CardFooter className="flex gap-2">
              <Button variant="outline">Change Plan</Button>
              <Button variant="outline">View Usage</Button>
            </CardFooter>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Payment Method</CardTitle>
              <CardDescription>
                Manage your payment information
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between p-3 rounded-lg border">
                <div className="flex items-center gap-3">
                  <CreditCard className="size-8 text-muted-foreground" />
                  <div>
                    <p className="font-medium">Visa ending in 4242</p>
                    <p className="text-sm text-muted-foreground">Expires 12/25</p>
                  </div>
                </div>
                <Button variant="outline" size="sm">
                  Update
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Team Tab */}
        <TabsContent value="team" className="space-y-6">
          {/* Workspace Settings Card */}
          <Card>
            <CardHeader>
              <CardTitle>Workspace Settings</CardTitle>
              <CardDescription>
                Manage your workspace details and configuration
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="workspaceName">Workspace Name</Label>
                <Input
                  id="workspaceName"
                  value={workspaceForm.name}
                  onChange={(e) =>
                    setWorkspaceEdits((prev) => ({
                      ...prev,
                      name: e.target.value,
                    }))
                  }
                  placeholder="My Workspace"
                  disabled={!canEditWorkspace}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="workspaceDescription">Description</Label>
                <Textarea
                  id="workspaceDescription"
                  value={workspaceForm.description}
                  onChange={(e) =>
                    setWorkspaceEdits((prev) => ({
                      ...prev,
                      description: e.target.value,
                    }))
                  }
                  placeholder="A brief description of this workspace..."
                  className="min-h-[80px]"
                  disabled={!canEditWorkspace}
                />
              </div>
              <Separator />
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>Default Workspace</Label>
                  <p className="text-sm text-muted-foreground">
                    Set this as your default workspace when you log in
                  </p>
                </div>
                <Switch
                  checked={currentWorkspace?.is_default ?? false}
                  onCheckedChange={() => setDefaultMutation.mutate()}
                  disabled={
                    setDefaultMutation.isPending || currentWorkspace?.is_default
                  }
                />
              </div>
              {!canEditWorkspace && (
                <p className="text-sm text-muted-foreground">
                  Only workspace owners and admins can edit these settings.
                </p>
              )}
            </CardContent>
            <CardFooter className="flex justify-between">
              <div>
                {canEditWorkspace && (
                  <Button
                    onClick={handleSaveWorkspace}
                    disabled={workspaceUpdateMutation.isPending}
                  >
                    {workspaceUpdateMutation.isPending ? (
                      <>
                        <Loader2 className="mr-2 size-4 animate-spin" />
                        Saving...
                      </>
                    ) : workspaceSaved ? (
                      <>
                        <Check className="mr-2 size-4" />
                        Saved
                      </>
                    ) : (
                      <>
                        <Save className="mr-2 size-4" />
                        Save Changes
                      </>
                    )}
                  </Button>
                )}
              </div>
              {canDeleteWorkspace && (
                <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
                  <AlertDialogTrigger asChild>
                    <Button variant="destructive">
                      <Trash2 className="mr-2 size-4" />
                      Delete Workspace
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Delete Workspace</AlertDialogTitle>
                      <AlertDialogDescription>
                        Are you sure you want to delete &quot;{currentWorkspace?.workspace.name}&quot;?
                        This action cannot be undone. All data including contacts, campaigns,
                        and team members will be permanently removed.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={handleDeleteWorkspace}
                        className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        disabled={workspaceDeleteMutation.isPending}
                      >
                        {workspaceDeleteMutation.isPending ? (
                          <>
                            <Loader2 className="mr-2 size-4 animate-spin" />
                            Deleting...
                          </>
                        ) : (
                          "Delete Workspace"
                        )}
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              )}
            </CardFooter>
          </Card>

          {/* Company Information Card */}
          <Card>
            <CardHeader>
              <CardTitle>Company Information</CardTitle>
              <CardDescription>
                Business details for this workspace (GoHighLevel-style subaccount info)
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="businessName">Business Name</Label>
                  <Input
                    id="businessName"
                    value={companyForm.business_name}
                    onChange={(e) =>
                      setCompanyEdits((prev) => ({
                        ...prev,
                        business_name: e.target.value,
                      }))
                    }
                    placeholder="Acme Inc."
                    disabled={!canEditWorkspace}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="companyPhone">Phone Number</Label>
                  <Input
                    id="companyPhone"
                    type="tel"
                    value={companyForm.phone}
                    onChange={(e) =>
                      setCompanyEdits((prev) => ({
                        ...prev,
                        phone: e.target.value,
                      }))
                    }
                    placeholder="+1 (555) 123-4567"
                    disabled={!canEditWorkspace}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="companyWebsite">Website</Label>
                <Input
                  id="companyWebsite"
                  type="url"
                  value={companyForm.website}
                  onChange={(e) =>
                    setCompanyEdits((prev) => ({
                      ...prev,
                      website: e.target.value,
                    }))
                  }
                  placeholder="https://example.com"
                  disabled={!canEditWorkspace}
                />
              </div>
              <Separator />
              <div className="space-y-2">
                <Label htmlFor="companyAddress">Street Address</Label>
                <Input
                  id="companyAddress"
                  value={companyForm.address}
                  onChange={(e) =>
                    setCompanyEdits((prev) => ({
                      ...prev,
                      address: e.target.value,
                    }))
                  }
                  placeholder="123 Main Street"
                  disabled={!canEditWorkspace}
                />
              </div>
              <div className="grid gap-4 md:grid-cols-3">
                <div className="space-y-2">
                  <Label htmlFor="companyCity">City</Label>
                  <Input
                    id="companyCity"
                    value={companyForm.city}
                    onChange={(e) =>
                      setCompanyEdits((prev) => ({
                        ...prev,
                        city: e.target.value,
                      }))
                    }
                    placeholder="San Francisco"
                    disabled={!canEditWorkspace}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="companyState">State / Province</Label>
                  <Input
                    id="companyState"
                    value={companyForm.state}
                    onChange={(e) =>
                      setCompanyEdits((prev) => ({
                        ...prev,
                        state: e.target.value,
                      }))
                    }
                    placeholder="CA"
                    disabled={!canEditWorkspace}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="companyPostalCode">Postal Code</Label>
                  <Input
                    id="companyPostalCode"
                    value={companyForm.postal_code}
                    onChange={(e) =>
                      setCompanyEdits((prev) => ({
                        ...prev,
                        postal_code: e.target.value,
                      }))
                    }
                    placeholder="94105"
                    disabled={!canEditWorkspace}
                  />
                </div>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="companyCountry">Country</Label>
                  <Input
                    id="companyCountry"
                    value={companyForm.country}
                    onChange={(e) =>
                      setCompanyEdits((prev) => ({
                        ...prev,
                        country: e.target.value,
                      }))
                    }
                    placeholder="United States"
                    disabled={!canEditWorkspace}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="companyTimezone">Timezone</Label>
                  <Select
                    value={companyForm.timezone}
                    onValueChange={(value) =>
                      setCompanyEdits((prev) => ({ ...prev, timezone: value }))
                    }
                    disabled={!canEditWorkspace}
                  >
                    <SelectTrigger id="companyTimezone">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {TIMEZONES.map((tz) => (
                        <SelectItem key={tz.value} value={tz.value}>
                          {tz.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              {!canEditWorkspace && (
                <p className="text-sm text-muted-foreground">
                  Only workspace owners and admins can edit company information.
                </p>
              )}
            </CardContent>
            <CardFooter>
              {canEditWorkspace && (
                <Button
                  onClick={handleSaveCompany}
                  disabled={companyUpdateMutation.isPending}
                >
                  {companyUpdateMutation.isPending ? (
                    <>
                      <Loader2 className="mr-2 size-4 animate-spin" />
                      Saving...
                    </>
                  ) : companySaved ? (
                    <>
                      <Check className="mr-2 size-4" />
                      Saved
                    </>
                  ) : (
                    <>
                      <Save className="mr-2 size-4" />
                      Save Company Info
                    </>
                  )}
                </Button>
              )}
            </CardFooter>
          </Card>

          {/* Team Members Card */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Team Members</CardTitle>
                  <CardDescription>
                    Manage who has access to your workspace
                  </CardDescription>
                </div>
                {canEditWorkspace && (
                  <Button onClick={() => setInviteDialogOpen(true)}>
                    <UserPlus className="mr-2 size-4" />
                    Invite Member
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {teamLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="size-6 animate-spin text-muted-foreground" />
                </div>
              ) : teamMembers && teamMembers.length > 0 ? (
                teamMembers.map((member) => (
                  <div
                    key={member.id}
                    className="flex items-center justify-between p-3 rounded-lg border"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex size-10 items-center justify-center rounded-full bg-primary/10 text-sm font-medium">
                        {getInitials(member.full_name, member.email)}
                      </div>
                      <div>
                        <p className="font-medium">
                          {member.full_name || member.email}
                        </p>
                        <p className="text-sm text-muted-foreground">
                          {member.email}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <Badge variant="outline" className="capitalize">
                        {member.role}
                      </Badge>
                      {canEditWorkspace && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleEditMember(member)}
                        >
                          Edit
                        </Button>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  No team members found
                </div>
              )}
            </CardContent>
          </Card>

          {/* Pending Invitations Card */}
          {canEditWorkspace && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Clock className="size-5" />
                  Pending Invitations
                </CardTitle>
                <CardDescription>
                  Invitations waiting to be accepted
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {invitationsLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="size-6 animate-spin text-muted-foreground" />
                  </div>
                ) : pendingInvitations && pendingInvitations.length > 0 ? (
                  pendingInvitations.map((invitation) => (
                    <div
                      key={invitation.id}
                      className="flex items-center justify-between p-3 rounded-lg border"
                    >
                      <div className="flex items-center gap-3">
                        <div className="flex size-10 items-center justify-center rounded-full bg-yellow-500/10 text-sm font-medium text-yellow-500">
                          <Mail className="size-5" />
                        </div>
                        <div>
                          <p className="font-medium">{invitation.email}</p>
                          <p className="text-sm text-muted-foreground">
                            Invited{" "}
                            {new Date(invitation.created_at).toLocaleDateString()}
                            {" · "}
                            Expires{" "}
                            {new Date(invitation.expires_at).toLocaleDateString()}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <Badge variant="outline" className="capitalize">
                          {invitation.role}
                        </Badge>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() =>
                            cancelInvitationMutation.mutate(invitation.id)
                          }
                          disabled={cancelInvitationMutation.isPending}
                        >
                          <X className="size-4" />
                        </Button>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    No pending invitations
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      {/* Integration Config Dialog */}
      {selectedIntegration && (
        <IntegrationConfigDialog
          open={integrationDialogOpen}
          onOpenChange={setIntegrationDialogOpen}
          integrationType={selectedIntegration}
          existingIntegration={getExistingIntegration(selectedIntegration)}
        />
      )}

      {/* Invite Member Dialog */}
      <InviteMemberDialog
        open={inviteDialogOpen}
        onOpenChange={setInviteDialogOpen}
      />

      {/* Edit Member Dialog */}
      {selectedMember && (
        <EditMemberDialog
          open={editMemberDialogOpen}
          onOpenChange={setEditMemberDialogOpen}
          member={selectedMember}
          currentUserRole={currentWorkspace?.role ?? "member"}
        />
      )}
    </div>
  );
}
