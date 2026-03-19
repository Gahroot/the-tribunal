"use client";

import { useState } from "react";
import { X, Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// Human-readable label for a number of minutes
export function formatMinutes(minutes: number): string {
  if (minutes < 60) return `${minutes} min before`;
  if (minutes % (24 * 60) === 0) {
    const days = minutes / (24 * 60);
    return `${days} day${days !== 1 ? "s" : ""} before`;
  }
  const hours = minutes / 60;
  if (Number.isInteger(hours)) return `${hours} hour${hours !== 1 ? "s" : ""} before`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${h}h ${m}m before`;
}

const PRESETS: { label: string; value: number }[] = [
  { label: "15 min before", value: 15 },
  { label: "30 min before", value: 30 },
  { label: "1 hour before", value: 60 },
  { label: "2 hours before", value: 120 },
  { label: "3 hours before", value: 180 },
  { label: "12 hours before", value: 720 },
  { label: "24 hours before", value: 1440 },
  { label: "48 hours before", value: 2880 },
  { label: "Custom...", value: -1 },
];

interface ReminderOffsetsInputProps {
  value: number[];
  onChange: (offsets: number[]) => void;
  disabled?: boolean;
}

export function ReminderOffsetsInput({
  value,
  onChange,
  disabled = false,
}: ReminderOffsetsInputProps) {
  const [showCustom, setShowCustom] = useState(false);
  const [customMinutes, setCustomMinutes] = useState("");
  const [customError, setCustomError] = useState("");

  const handleSelectPreset = (raw: string) => {
    const preset = parseInt(raw);
    if (preset === -1) {
      setShowCustom(true);
      return;
    }
    setShowCustom(false);
    if (value.includes(preset)) return; // no duplicates
    onChange([...value, preset].sort((a, b) => b - a));
  };

  const handleAddCustom = () => {
    const mins = parseInt(customMinutes);
    if (isNaN(mins) || mins < 1 || mins > 10080) {
      setCustomError("Enter a number between 1 and 10080 minutes");
      return;
    }
    if (value.includes(mins)) {
      setCustomError("This offset is already added");
      return;
    }
    onChange([...value, mins].sort((a, b) => b - a));
    setCustomMinutes("");
    setCustomError("");
    setShowCustom(false);
  };

  const handleRemove = (minutes: number) => {
    onChange(value.filter((v) => v !== minutes));
  };

  return (
    <div className="space-y-2">
      {/* Current offsets as chips */}
      {value.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {value.map((minutes) => (
            <Badge
              key={minutes}
              variant="secondary"
              className="flex items-center gap-1 px-2 py-1 text-xs"
            >
              {formatMinutes(minutes)}
              {!disabled && (
                <button
                  type="button"
                  onClick={() => handleRemove(minutes)}
                  className="ml-0.5 rounded-full hover:text-destructive focus:outline-none"
                  aria-label={`Remove ${formatMinutes(minutes)}`}
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </Badge>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground italic">
          No reminders configured — add at least one
        </p>
      )}

      {/* Add offset row */}
      {!disabled && (
        <div className="flex items-center gap-2">
          <Select onValueChange={handleSelectPreset} value="">
            <SelectTrigger className="h-8 w-[200px]">
              <SelectValue placeholder="+ Add reminder time" />
            </SelectTrigger>
            <SelectContent>
              {PRESETS.filter((p) => p.value === -1 || !value.includes(p.value)).map((p) => (
                <SelectItem key={p.value} value={String(p.value)}>
                  {p.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Custom minutes input */}
      {showCustom && !disabled && (
        <div className="flex items-center gap-2">
          <Input
            type="number"
            min={1}
            max={10080}
            placeholder="Minutes (1–10080)"
            className="h-8 w-[180px]"
            value={customMinutes}
            onChange={(e) => {
              setCustomMinutes(e.target.value);
              setCustomError("");
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                handleAddCustom();
              }
            }}
          />
          <Button type="button" size="sm" className="h-8" onClick={handleAddCustom}>
            <Plus className="mr-1 h-3 w-3" />
            Add
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8"
            onClick={() => {
              setShowCustom(false);
              setCustomMinutes("");
              setCustomError("");
            }}
          >
            Cancel
          </Button>
        </div>
      )}
      {customError && <p className="text-xs text-destructive">{customError}</p>}
    </div>
  );
}
