"use client";

import { Layers, Loader2 } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useSegments } from "@/hooks/useSegments";

interface SegmentPickerProps {
  workspaceId: string;
  selectedSegmentId: string | null;
  onSegmentSelect: (segmentId: string | null) => void;
}

export function SegmentPicker({
  workspaceId,
  selectedSegmentId,
  onSegmentSelect,
}: SegmentPickerProps) {
  const { data: segmentsData, isLoading } = useSegments(workspaceId);
  const segments = segmentsData?.items ?? [];

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading segments...
      </div>
    );
  }

  if (segments.length === 0) {
    return null;
  }

  return (
    <Select
      value={selectedSegmentId ?? "none"}
      onValueChange={(v) => onSegmentSelect(v === "none" ? null : v)}
    >
      <SelectTrigger className="w-full">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4" />
          <SelectValue placeholder="Use a saved segment..." />
        </div>
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="none">No segment</SelectItem>
        {segments.map((segment) => (
          <SelectItem key={segment.id} value={segment.id}>
            <div className="flex items-center justify-between w-full gap-2">
              <span>{segment.name}</span>
              <span className="text-xs text-muted-foreground">
                {segment.contact_count.toLocaleString()}
              </span>
            </div>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
