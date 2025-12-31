"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import {
  User,
  Bell,
  Phone,
  Mail,
  Calendar,
  Shield,
  Palette,
  Globe,
  Webhook,
  Key,
  CreditCard,
  Building2,
  Save,
  ExternalLink,
  Check,
  AlertCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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

const settingsTabs = [
  { value: "profile", label: "Profile", icon: User },
  { value: "notifications", label: "Notifications", icon: Bell },
  { value: "integrations", label: "Integrations", icon: Webhook },
  { value: "billing", label: "Billing", icon: CreditCard },
  { value: "team", label: "Team", icon: Building2 },
];

export function SettingsPage() {
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
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
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="firstName">First Name</Label>
                  <Input id="firstName" defaultValue="John" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="lastName">Last Name</Label>
                  <Input id="lastName" defaultValue="Doe" />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" defaultValue="john@company.com" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="phone">Phone Number</Label>
                <Input id="phone" type="tel" defaultValue="+1 (555) 123-4567" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="timezone">Timezone</Label>
                <Select defaultValue="america-new-york">
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="america-new-york">
                      America/New York (EST)
                    </SelectItem>
                    <SelectItem value="america-chicago">
                      America/Chicago (CST)
                    </SelectItem>
                    <SelectItem value="america-denver">
                      America/Denver (MST)
                    </SelectItem>
                    <SelectItem value="america-los-angeles">
                      America/Los Angeles (PST)
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
            <CardFooter>
              <Button onClick={handleSave}>
                {saved ? (
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
              {[
                { id: "new-leads", label: "New Leads", description: "When a new lead is created" },
                { id: "campaign-complete", label: "Campaign Complete", description: "When a campaign finishes" },
                { id: "call-summary", label: "Call Summaries", description: "Daily summary of AI calls" },
                { id: "weekly-report", label: "Weekly Reports", description: "Weekly performance digest" },
              ].map((item) => (
                <div key={item.id} className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>{item.label}</Label>
                    <p className="text-sm text-muted-foreground">
                      {item.description}
                    </p>
                  </div>
                  <Switch defaultChecked={item.id !== "weekly-report"} />
                </div>
              ))}
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
              {[
                { id: "incoming-call", label: "Incoming Calls", description: "Alert when a call comes in" },
                { id: "new-message", label: "New Messages", description: "Alert for new SMS/email replies" },
                { id: "ai-handoff", label: "AI Handoffs", description: "When AI needs human assistance" },
              ].map((item) => (
                <div key={item.id} className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label>{item.label}</Label>
                    <p className="text-sm text-muted-foreground">
                      {item.description}
                    </p>
                  </div>
                  <Switch defaultChecked />
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Integrations Tab */}
        <TabsContent value="integrations" className="space-y-6">
          <div className="grid gap-4 md:grid-cols-2">
            {/* Cal.com Integration */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex size-10 items-center justify-center rounded-lg bg-primary/10">
                      <Calendar className="size-5 text-primary" />
                    </div>
                    <div>
                      <CardTitle className="text-base">Cal.com</CardTitle>
                      <CardDescription>Appointment scheduling</CardDescription>
                    </div>
                  </div>
                  <Badge className="bg-green-500/10 text-green-500 border-green-500/20">
                    Connected
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Sync your calendar and let AI agents book appointments automatically.
                </p>
              </CardContent>
              <CardFooter>
                <Button variant="outline" size="sm">
                  Configure
                </Button>
              </CardFooter>
            </Card>

            {/* Twilio Integration */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex size-10 items-center justify-center rounded-lg bg-red-500/10">
                      <Phone className="size-5 text-red-500" />
                    </div>
                    <div>
                      <CardTitle className="text-base">Twilio</CardTitle>
                      <CardDescription>Voice & SMS provider</CardDescription>
                    </div>
                  </div>
                  <Badge className="bg-green-500/10 text-green-500 border-green-500/20">
                    Connected
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Power your voice calls and SMS messages with Twilio.
                </p>
              </CardContent>
              <CardFooter>
                <Button variant="outline" size="sm">
                  Configure
                </Button>
              </CardFooter>
            </Card>

            {/* SendGrid Integration */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex size-10 items-center justify-center rounded-lg bg-blue-500/10">
                      <Mail className="size-5 text-blue-500" />
                    </div>
                    <div>
                      <CardTitle className="text-base">SendGrid</CardTitle>
                      <CardDescription>Email delivery</CardDescription>
                    </div>
                  </div>
                  <Badge variant="outline">Not Connected</Badge>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Send email campaigns through SendGrid for better deliverability.
                </p>
              </CardContent>
              <CardFooter>
                <Button size="sm">Connect</Button>
              </CardFooter>
            </Card>

            {/* Webhook Integration */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex size-10 items-center justify-center rounded-lg bg-purple-500/10">
                      <Webhook className="size-5 text-purple-500" />
                    </div>
                    <div>
                      <CardTitle className="text-base">Webhooks</CardTitle>
                      <CardDescription>Custom integrations</CardDescription>
                    </div>
                  </div>
                  <Badge className="bg-green-500/10 text-green-500 border-green-500/20">
                    2 Active
                  </Badge>
                </div>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Send real-time events to your own endpoints.
                </p>
              </CardContent>
              <CardFooter>
                <Button variant="outline" size="sm">
                  Manage
                </Button>
              </CardFooter>
            </Card>
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
              <Button variant="outline">
                Generate New Key
              </Button>
            </CardFooter>
          </Card>
        </TabsContent>

        {/* Billing Tab */}
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
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Team Members</CardTitle>
                  <CardDescription>
                    Manage who has access to your workspace
                  </CardDescription>
                </div>
                <Button>Invite Member</Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {[
                { name: "John Doe", email: "john@company.com", role: "Owner", initials: "JD" },
                { name: "Jane Smith", email: "jane@company.com", role: "Admin", initials: "JS" },
                { name: "Bob Wilson", email: "bob@company.com", role: "Member", initials: "BW" },
              ].map((member) => (
                <div
                  key={member.email}
                  className="flex items-center justify-between p-3 rounded-lg border"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex size-10 items-center justify-center rounded-full bg-primary/10 text-sm font-medium">
                      {member.initials}
                    </div>
                    <div>
                      <p className="font-medium">{member.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {member.email}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge variant="outline">{member.role}</Badge>
                    <Button variant="ghost" size="sm">
                      Edit
                    </Button>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
