"use client";

import type { ValueStackItem } from "@/types";

import { ValueStackBuilder } from "./value-stack-builder";

interface ValueStackStepProps {
  items: ValueStackItem[];
  onChange: (items: ValueStackItem[]) => void;
}

export function ValueStackStep({ items, onChange }: ValueStackStepProps) {
  return <ValueStackBuilder items={items} onChange={onChange} />;
}
