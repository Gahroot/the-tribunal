"use client";

import { useState } from "react";
import { Loader2, Tags } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { TagPicker } from "@/components/tags/tag-picker";
import { TagBadge } from "@/components/tags/tag-badge";
import { useTags, useBulkTagContacts } from "@/hooks/useTags";

interface BulkTagDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedContactIds: number[];
  workspaceId: string;
}

export function BulkTagDialog({
  open,
  onOpenChange,
  selectedContactIds,
  workspaceId,
}: BulkTagDialogProps) {
  const [addTagIds, setAddTagIds] = useState<string[]>([]);
  const [removeTagIds, setRemoveTagIds] = useState<string[]>([]);
  const { data: tagsData } = useTags(workspaceId);
  const bulkTagMutation = useBulkTagContacts(workspaceId);

  const tags = tagsData?.items ?? [];

  const handleApply = async () => {
    if (addTagIds.length === 0 && removeTagIds.length === 0) return;
    try {
      await bulkTagMutation.mutateAsync({
        contact_ids: selectedContactIds,
        add_tag_ids: addTagIds.length > 0 ? addTagIds : undefined,
        remove_tag_ids: removeTagIds.length > 0 ? removeTagIds : undefined,
      });
      toast.success("Tags updated");
      onOpenChange(false);
      setAddTagIds([]);
      setRemoveTagIds([]);
    } catch {
      toast.error("Failed to update tags");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Tags className="h-5 w-5" />
            Tag {selectedContactIds.length} contact{selectedContactIds.length !== 1 ? "s" : ""}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          {/* Add tags */}
          <div className="space-y-2">
            <Label>Add tags</Label>
            <TagPicker
              workspaceId={workspaceId}
              selectedTagIds={addTagIds}
              onSelectionChange={setAddTagIds}
              allowCreate
            />
            {addTagIds.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {addTagIds.map((id) => {
                  const tag = tags.find((t) => t.id === id);
                  if (!tag) return null;
                  return (
                    <TagBadge
                      key={tag.id}
                      name={tag.name}
                      color={tag.color}
                      onRemove={() => setAddTagIds(addTagIds.filter((i) => i !== id))}
                    />
                  );
                })}
              </div>
            )}
          </div>

          {/* Remove tags */}
          <div className="space-y-2">
            <Label>Remove tags</Label>
            <TagPicker
              workspaceId={workspaceId}
              selectedTagIds={removeTagIds}
              onSelectionChange={setRemoveTagIds}
              allowCreate={false}
            />
            {removeTagIds.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {removeTagIds.map((id) => {
                  const tag = tags.find((t) => t.id === id);
                  if (!tag) return null;
                  return (
                    <TagBadge
                      key={tag.id}
                      name={tag.name}
                      color={tag.color}
                      onRemove={() => setRemoveTagIds(removeTagIds.filter((i) => i !== id))}
                    />
                  );
                })}
              </div>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleApply}
            disabled={
              (addTagIds.length === 0 && removeTagIds.length === 0) ||
              bulkTagMutation.isPending
            }
          >
            {bulkTagMutation.isPending && (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            )}
            Apply
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
