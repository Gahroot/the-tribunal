"use client";

import { Plus, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import {
  DISPLAY_OPTIONS,
  MODE_OPTIONS,
  POSITION_OPTIONS,
  THEME_OPTIONS,
  type EmbedFormValues,
} from "./embed-types";

interface EmbedConfigFormProps {
  values: EmbedFormValues;
  onChange: (patch: Partial<EmbedFormValues>) => void;
  newDomain: string;
  onNewDomainChange: (value: string) => void;
  onAddDomain: () => void;
  onRemoveDomain: (domain: string) => void;
}

/**
 * Editable settings panel for the embed-agent dialog. All state is owned by
 * the parent (`EmbedAgentDialog`) and pushed in via `values` / `onChange`,
 * keeping this component a pure controlled form.
 */
export function EmbedConfigForm({
  values,
  onChange,
  newDomain,
  onNewDomainChange,
  onAddDomain,
  onRemoveDomain,
}: EmbedConfigFormProps) {
  return (
    <div className="space-y-6">
      {/* Domain allowlist */}
      <div className="space-y-3">
        <Label>Allowed Domains</Label>
        <p className="text-xs text-muted-foreground">
          Specify which domains can embed this agent. Use *.example.com for
          subdomains.
        </p>
        <div className="flex gap-2">
          <Input
            placeholder="example.com"
            value={newDomain}
            onChange={(e) => onNewDomainChange(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onAddDomain()}
          />
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={onAddDomain}
            aria-label="Add domain"
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        {values.allowedDomains.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {values.allowedDomains.map((domain) => (
              <Badge key={domain} variant="secondary" className="gap-1">
                {domain}
                <button
                  type="button"
                  onClick={() => onRemoveDomain(domain)}
                  className="ml-1 rounded-full hover:bg-destructive/20"
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            ))}
          </div>
        )}
      </div>

      {/* Settings grid */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label>Mode</Label>
          <Select
            value={values.mode}
            onValueChange={(v) => onChange({ mode: v })}
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
          <Label>Display</Label>
          <Select
            value={values.display}
            onValueChange={(v) => onChange({ display: v })}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {DISPLAY_OPTIONS.map((opt) => (
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
            value={values.position}
            onValueChange={(v) => onChange({ position: v })}
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
            value={values.theme}
            onValueChange={(v) => onChange({ theme: v })}
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
              value={values.primaryColor}
              onChange={(e) => onChange({ primaryColor: e.target.value })}
              className="h-10 w-14 cursor-pointer p-1"
            />
            <Input
              value={values.primaryColor}
              onChange={(e) => onChange({ primaryColor: e.target.value })}
              className="font-mono"
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label>Button Text</Label>
          <Input
            value={values.buttonText}
            onChange={(e) => onChange({ buttonText: e.target.value })}
            placeholder="Talk to AI"
          />
        </div>
      </div>
    </div>
  );
}
