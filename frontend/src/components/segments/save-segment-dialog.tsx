"use client";

import { Loader2, Save, Users } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useCreateSegment, useSegmentPreview } from "@/hooks/useSegments";
import { formatNumber } from "@/lib/utils/number";
import type { FilterDefinition } from "@/types";

interface SaveSegmentDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  filters: FilterDefinition;
  workspaceId: string;
}

export function SaveSegmentDialog({
  open,
  onOpenChange,
  filters,
  workspaceId,
}: SaveSegmentDialogProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const createSegment = useCreateSegment(workspaceId);
  const { data: preview, isFetching: isPreviewFetching } = useSegmentPreview(
    workspaceId,
    open ? filters : null,
  );

  const handleSave = async () => {
    if (!name.trim()) return;
    try {
      await createSegment.mutateAsync({
        name: name.trim(),
        description: description.trim() || undefined,
        definition: filters,
      });
      toast.success("Segment saved");
      onOpenChange(false);
      setName("");
      setDescription("");
    } catch {
      toast.error("Failed to save segment");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Save className="h-5 w-5" />
            Save as Segment
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="segment-name">Name</Label>
            <Input
              id="segment-name"
              placeholder="e.g., High-value leads"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSave();
              }}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="segment-desc">Description (optional)</Label>
            <Textarea
              id="segment-desc"
              placeholder="Describe this segment..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
            />
          </div>
          <div className="text-sm text-muted-foreground bg-muted/50 rounded-lg p-3">
            <p className="font-medium mb-1">Filter rules ({filters.rules.length})</p>
            <p>
              Logic: {filters.logic === "or" ? "Match any" : "Match all"} rule
              {filters.rules.length !== 1 ? "s" : ""}
            </p>
            <p className="mt-2 flex items-center gap-2 text-foreground">
              {isPreviewFetching ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Users className="h-3.5 w-3.5" />
              )}
              <span>
                {preview
                  ? `~${formatNumber(preview.total)} contact${
                      preview.total === 1 ? "" : "s"
                    } match`
                  : "Counting matches…"}
              </span>
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={!name.trim() || createSegment.isPending}
          >
            {createSegment.isPending && (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            )}
            Save Segment
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
