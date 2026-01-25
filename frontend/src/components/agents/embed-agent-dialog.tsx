"use client";

import { useState, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Copy, Check, ExternalLink, Plus, X, Code2 } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { agentsApi, type EmbedSettingsUpdate } from "@/lib/api/agents";

interface EmbedAgentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agentId: string;
  agentName: string;
  workspaceId: string;
}

const POSITION_OPTIONS = [
  { value: "bottom-right", label: "Bottom Right" },
  { value: "bottom-left", label: "Bottom Left" },
  { value: "top-right", label: "Top Right" },
  { value: "top-left", label: "Top Left" },
];

const THEME_OPTIONS = [
  { value: "auto", label: "Auto (System)" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

const MODE_OPTIONS = [
  { value: "voice", label: "Voice Only" },
  { value: "chat", label: "Chat Only" },
  { value: "both", label: "Both" },
];

// Inner component that manages its own form state
function EmbedDialogContent({
  onClose,
  agentId,
  agentName,
  workspaceId,
}: {
  onClose: () => void;
  agentId: string;
  agentName: string;
  workspaceId: string;
}) {
  const queryClient = useQueryClient();
  const [copied, setCopied] = useState(false);
  const [newDomain, setNewDomain] = useState("");

  // Fetch embed settings
  const { data: embedSettings, isLoading } = useQuery({
    queryKey: ["agent-embed", workspaceId, agentId],
    queryFn: () => agentsApi.getEmbedSettings(workspaceId, agentId),
  });

  // Form state - track local changes from the base data
  const [localChanges, setLocalChanges] = useState<{
    embedEnabled?: boolean;
    allowedDomains?: string[];
    buttonText?: string;
    theme?: string;
    position?: string;
    primaryColor?: string;
    mode?: string;
  }>({});

  // Compute current values (base from server + local changes)
  const currentValues = useMemo(() => {
    const base = embedSettings ?? {
      embed_enabled: false,
      allowed_domains: [],
      embed_settings: {
        button_text: "Talk to AI",
        theme: "auto",
        position: "bottom-right",
        primary_color: "#6366f1",
        mode: "voice",
      },
    };

    return {
      embedEnabled: localChanges.embedEnabled ?? base.embed_enabled,
      allowedDomains: localChanges.allowedDomains ?? base.allowed_domains,
      buttonText: localChanges.buttonText ?? base.embed_settings.button_text,
      theme: localChanges.theme ?? base.embed_settings.theme,
      position: localChanges.position ?? base.embed_settings.position,
      primaryColor: localChanges.primaryColor ?? base.embed_settings.primary_color,
      mode: localChanges.mode ?? base.embed_settings.mode,
    };
  }, [embedSettings, localChanges]);

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: (data: EmbedSettingsUpdate) =>
      agentsApi.updateEmbedSettings(workspaceId, agentId, data),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["agent-embed", workspaceId, agentId],
      });
      toast.success("Embed settings saved");
      setLocalChanges({});
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "Failed to save settings");
    },
  });

  const handleSave = () => {
    updateMutation.mutate({
      embed_enabled: currentValues.embedEnabled,
      allowed_domains: currentValues.allowedDomains,
      embed_settings: {
        button_text: currentValues.buttonText,
        theme: currentValues.theme,
        position: currentValues.position,
        primary_color: currentValues.primaryColor,
        mode: currentValues.mode,
      },
    });
  };

  const addDomain = () => {
    if (!newDomain.trim()) return;
    const domain = newDomain.trim().toLowerCase();
    if (!currentValues.allowedDomains.includes(domain)) {
      setLocalChanges({
        ...localChanges,
        allowedDomains: [...currentValues.allowedDomains, domain],
      });
    }
    setNewDomain("");
  };

  const removeDomain = (domain: string) => {
    setLocalChanges({
      ...localChanges,
      allowedDomains: currentValues.allowedDomains.filter((d) => d !== domain),
    });
  };

  const copyToClipboard = (text: string) => {
    void navigator.clipboard.writeText(text);
    setCopied(true);
    toast.success("Copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  };

  // Generate embed code
  const baseUrl = typeof window !== "undefined" ? window.location.origin : "";
  const publicId = embedSettings?.public_id || "";

  const scriptCode = `<script src="${baseUrl}/widget/v1/widget.js" defer></script>
<ai-agent agent-id="${publicId}" mode="${currentValues.mode}"></ai-agent>`;

  const iframeCode = `<iframe
  src="${baseUrl}/embed/${publicId}${currentValues.mode === "chat" ? "/chat" : ""}?theme=${currentValues.theme}"
  width="400"
  height="600"
  allow="microphone"
  style="border: none; border-radius: 16px;"
></iframe>`;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          <Code2 className="h-5 w-5" />
          Embed {agentName}
        </DialogTitle>
        <DialogDescription>
          Add this AI agent to your website with a simple script tag or iframe.
        </DialogDescription>
      </DialogHeader>

      <div className="space-y-6">
        {/* Enable toggle */}
        <div className="flex items-center justify-between rounded-lg border p-4">
          <div className="space-y-0.5">
            <Label className="text-base font-medium">Enable Embedding</Label>
            <p className="text-sm text-muted-foreground">
              Allow this agent to be embedded on external websites
            </p>
          </div>
          <Switch
            checked={currentValues.embedEnabled}
            onCheckedChange={(v) => setLocalChanges({ ...localChanges, embedEnabled: v })}
          />
        </div>

        {currentValues.embedEnabled && (
          <>
            {/* Domain allowlist */}
            <div className="space-y-3">
              <Label>Allowed Domains</Label>
              <p className="text-xs text-muted-foreground">
                Specify which domains can embed this agent. Use *.example.com for subdomains.
              </p>
              <div className="flex gap-2">
                <Input
                  placeholder="example.com"
                  value={newDomain}
                  onChange={(e) => setNewDomain(e.target.value)}
                  onKeyPress={(e) => e.key === "Enter" && addDomain()}
                />
                <Button type="button" variant="outline" size="icon" onClick={addDomain}>
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
              {currentValues.allowedDomains.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {currentValues.allowedDomains.map((domain) => (
                    <Badge key={domain} variant="secondary" className="gap-1">
                      {domain}
                      <button
                        type="button"
                        onClick={() => removeDomain(domain)}
                        className="ml-1 rounded-full hover:bg-destructive/20"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
              )}
            </div>

            {/* Settings */}
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Mode</Label>
                <Select
                  value={currentValues.mode}
                  onValueChange={(v) => setLocalChanges({ ...localChanges, mode: v })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {MODE_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Position</Label>
                <Select
                  value={currentValues.position}
                  onValueChange={(v) => setLocalChanges({ ...localChanges, position: v })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {POSITION_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Theme</Label>
                <Select
                  value={currentValues.theme}
                  onValueChange={(v) => setLocalChanges({ ...localChanges, theme: v })}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {THEME_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Primary Color</Label>
                <div className="flex gap-2">
                  <Input
                    type="color"
                    value={currentValues.primaryColor}
                    onChange={(e) =>
                      setLocalChanges({ ...localChanges, primaryColor: e.target.value })
                    }
                    className="h-10 w-14 cursor-pointer p-1"
                  />
                  <Input
                    value={currentValues.primaryColor}
                    onChange={(e) =>
                      setLocalChanges({ ...localChanges, primaryColor: e.target.value })
                    }
                    className="font-mono"
                  />
                </div>
              </div>

              <div className="space-y-2 sm:col-span-2">
                <Label>Button Text</Label>
                <Input
                  value={currentValues.buttonText}
                  onChange={(e) =>
                    setLocalChanges({ ...localChanges, buttonText: e.target.value })
                  }
                  placeholder="Talk to AI"
                />
              </div>
            </div>

            {/* Embed code */}
            <Tabs defaultValue="script" className="w-full">
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="script">Script Tag</TabsTrigger>
                <TabsTrigger value="iframe">Iframe</TabsTrigger>
              </TabsList>

              <TabsContent value="script" className="space-y-2">
                <div className="relative">
                  <pre className="overflow-x-auto rounded-lg bg-muted p-4 text-xs">
                    {scriptCode}
                  </pre>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="absolute right-2 top-2 h-8 w-8"
                    onClick={() => copyToClipboard(scriptCode)}
                  >
                    {copied ? (
                      <Check className="h-4 w-4 text-green-500" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Add this code before the closing {`</body>`} tag of your website.
                </p>
              </TabsContent>

              <TabsContent value="iframe" className="space-y-2">
                <div className="relative">
                  <pre className="overflow-x-auto rounded-lg bg-muted p-4 text-xs">
                    {iframeCode}
                  </pre>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="absolute right-2 top-2 h-8 w-8"
                    onClick={() => copyToClipboard(iframeCode)}
                  >
                    {copied ? (
                      <Check className="h-4 w-4 text-green-500" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Use this iframe to embed the agent directly on your page.
                </p>
              </TabsContent>
            </Tabs>

            {/* Preview button */}
            {publicId && (
              <Button variant="outline" className="w-full" asChild>
                <a
                  href={`/embed/${publicId}${currentValues.mode === "chat" ? "/chat" : ""}?theme=${currentValues.theme}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <ExternalLink className="mr-2 h-4 w-4" />
                  Preview Embed
                </a>
              </Button>
            )}
          </>
        )}

        {/* Save button */}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={updateMutation.isPending}>
            {updateMutation.isPending ? "Saving..." : "Save Changes"}
          </Button>
        </div>
      </div>
    </>
  );
}

export function EmbedAgentDialog({
  open,
  onOpenChange,
  agentId,
  agentName,
  workspaceId,
}: EmbedAgentDialogProps) {
  // Use key to reset state when dialog opens
  const [dialogKey, setDialogKey] = useState(0);

  const handleOpenChange = (newOpen: boolean) => {
    if (newOpen) {
      setDialogKey((k) => k + 1);
    }
    onOpenChange(newOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[600px]">
        {open ? (
          <EmbedDialogContent
            key={dialogKey}
            onClose={() => onOpenChange(false)}
            agentId={agentId}
            agentName={agentName}
            workspaceId={workspaceId}
          />
        ) : (
          <DialogTitle className="sr-only">Embed Agent</DialogTitle>
        )}
      </DialogContent>
    </Dialog>
  );
}
