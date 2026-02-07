"use client";

import { Phone } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import type { PhoneNumber } from "@/types";

interface BasicsStepProps {
  name: string;
  description: string;
  fromPhoneNumber: string;
  phoneNumbers: PhoneNumber[];
  errors: Record<string, string>;
  onNameChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onPhoneChange: (value: string) => void;
  namePlaceholder?: string;
  emptyPhoneLabel?: string;
}

export function BasicsStep({
  name,
  description,
  fromPhoneNumber,
  phoneNumbers,
  errors,
  onNameChange,
  onDescriptionChange,
  onPhoneChange,
  namePlaceholder = "e.g., Campaign Name",
  emptyPhoneLabel = "No phone numbers available",
}: BasicsStepProps) {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Label htmlFor="campaign-name">Campaign Name *</Label>
        <Input
          id="campaign-name"
          placeholder={namePlaceholder}
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          className={errors.name ? "border-destructive" : ""}
        />
        {errors.name && (
          <p className="text-sm text-destructive">{errors.name}</p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="campaign-description">Description</Label>
        <Textarea
          id="campaign-description"
          placeholder="Brief description of this campaign..."
          value={description}
          onChange={(e) => onDescriptionChange(e.target.value)}
          rows={3}
        />
      </div>

      <div className="space-y-2">
        <Label>From Phone Number *</Label>
        <Select value={fromPhoneNumber} onValueChange={onPhoneChange}>
          <SelectTrigger
            className={errors.from_phone_number ? "border-destructive" : ""}
          >
            <SelectValue placeholder="Select a phone number" />
          </SelectTrigger>
          <SelectContent>
            {phoneNumbers.map((phone) => (
              <SelectItem key={phone.id} value={phone.phone_number}>
                <div className="flex items-center gap-2">
                  <Phone className="size-4" />
                  <span>{phone.phone_number}</span>
                  {phone.friendly_name && (
                    <span className="text-muted-foreground">
                      ({phone.friendly_name})
                    </span>
                  )}
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {errors.from_phone_number && (
          <p className="text-sm text-destructive">
            {errors.from_phone_number}
          </p>
        )}
        {phoneNumbers.length === 0 && (
          <p className="text-sm text-muted-foreground">{emptyPhoneLabel}</p>
        )}
      </div>
    </div>
  );
}
