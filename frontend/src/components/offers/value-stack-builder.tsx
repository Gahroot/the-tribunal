"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Plus,
  Trash2,
  GripVertical,
  DollarSign,
  CheckCircle,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent } from "@/components/ui/card";
import type { ValueStackItem } from "@/types";

interface ValueStackBuilderProps {
  items: ValueStackItem[];
  onChange: (items: ValueStackItem[]) => void;
}

export function ValueStackBuilder({ items, onChange }: ValueStackBuilderProps) {
  const [editingIndex, setEditingIndex] = useState<number | null>(null);

  const addItem = () => {
    onChange([
      ...items,
      {
        name: "",
        description: "",
        value: 0,
        included: true,
      },
    ]);
    setEditingIndex(items.length);
  };

  const updateItem = (index: number, updates: Partial<ValueStackItem>) => {
    const newItems = [...items];
    newItems[index] = { ...newItems[index], ...updates };
    onChange(newItems);
  };

  const removeItem = (index: number) => {
    onChange(items.filter((_, i) => i !== index));
    if (editingIndex === index) {
      setEditingIndex(null);
    }
  };

  const moveItem = (fromIndex: number, toIndex: number) => {
    if (toIndex < 0 || toIndex >= items.length) return;
    const newItems = [...items];
    const [movedItem] = newItems.splice(fromIndex, 1);
    newItems.splice(toIndex, 0, movedItem);
    onChange(newItems);
  };

  const totalValue = items
    .filter((item) => item.included)
    .reduce((sum, item) => sum + (item.value || 0), 0);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <Label className="text-base font-medium">Value Stack Items</Label>
          <p className="text-sm text-muted-foreground">
            Add items to show the total value of your offer
          </p>
        </div>
        <div className="text-right">
          <p className="text-sm text-muted-foreground">Total Value</p>
          <p className="text-2xl font-bold text-green-600">
            ${totalValue.toLocaleString()}
          </p>
        </div>
      </div>

      <AnimatePresence mode="popLayout">
        {items.map((item, index) => (
          <motion.div
            key={index}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, x: -100 }}
            layout
          >
            <Card
              className={`transition-colors ${
                !item.included ? "opacity-60" : ""
              }`}
            >
              <CardContent className="p-4">
                <div className="flex items-start gap-3">
                  {/* Drag handle */}
                  <div className="flex flex-col gap-1 pt-2">
                    <button
                      type="button"
                      onClick={() => moveItem(index, index - 1)}
                      disabled={index === 0}
                      className="p-1 text-muted-foreground hover:text-foreground disabled:opacity-30"
                    >
                      <GripVertical className="size-4" />
                    </button>
                  </div>

                  {/* Content */}
                  <div className="flex-1 space-y-3">
                    <div className="flex items-center gap-3">
                      <Input
                        placeholder="Item name (e.g., Video Training Series)"
                        value={item.name}
                        onChange={(e) =>
                          updateItem(index, { name: e.target.value })
                        }
                        className="flex-1"
                      />
                      <div className="flex items-center gap-1">
                        <DollarSign className="size-4 text-muted-foreground" />
                        <Input
                          type="number"
                          min="0"
                          placeholder="Value"
                          value={item.value || ""}
                          onChange={(e) =>
                            updateItem(index, {
                              value: parseFloat(e.target.value) || 0,
                            })
                          }
                          className="w-24"
                        />
                      </div>
                    </div>

                    <Input
                      placeholder="Description (optional)"
                      value={item.description || ""}
                      onChange={(e) =>
                        updateItem(index, { description: e.target.value })
                      }
                      className="text-sm"
                    />

                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Switch
                          checked={item.included}
                          onCheckedChange={(checked) =>
                            updateItem(index, { included: checked })
                          }
                        />
                        <span className="text-sm text-muted-foreground">
                          {item.included ? (
                            <span className="flex items-center gap-1 text-green-600">
                              <CheckCircle className="size-3" />
                              Included in offer
                            </span>
                          ) : (
                            <span className="flex items-center gap-1 text-muted-foreground">
                              <XCircle className="size-3" />
                              Excluded
                            </span>
                          )}
                        </span>
                      </div>

                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => removeItem(index)}
                        className="text-destructive hover:text-destructive"
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </AnimatePresence>

      <Button
        type="button"
        variant="outline"
        onClick={addItem}
        className="w-full"
      >
        <Plus className="size-4 mr-2" />
        Add Value Stack Item
      </Button>

      {items.length > 0 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="p-4 bg-gradient-to-r from-green-500/10 to-emerald-500/10 rounded-lg border border-green-500/20"
        >
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium text-green-700 dark:text-green-400">
                Total Stack Value
              </p>
              <p className="text-sm text-muted-foreground">
                {items.filter((i) => i.included).length} of {items.length} items
                included
              </p>
            </div>
            <div className="text-right">
              <p className="text-3xl font-bold text-green-600">
                ${totalValue.toLocaleString()}
              </p>
              <p className="text-xs text-muted-foreground">perceived value</p>
            </div>
          </div>
        </motion.div>
      )}
    </div>
  );
}
