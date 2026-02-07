"use client";

import { ValueStackBuilder } from "./value-stack-builder";
import type { ValueStackItem } from "@/types";

interface ValueStackStepProps {
  items: ValueStackItem[];
  onChange: (items: ValueStackItem[]) => void;
}

export function ValueStackStep({ items, onChange }: ValueStackStepProps) {
  return <ValueStackBuilder items={items} onChange={onChange} />;
}
