"use client";

import { X } from "lucide-react";
import type { FilterRule } from "@/types";

interface FilterChipProps {
  rule: FilterRule;
  onRemove: () => void;
}

const FIELD_LABELS: Record<string, string> = {
  status: "Status",
  tags: "Tags",
  lead_score: "Lead Score",
  is_qualified: "Qualified",
  source: "Source",
  company_name: "Company",
  created_at: "Created",
  enrichment_status: "Enrichment",
  email: "Email",
  first_name: "First Name",
  last_name: "Last Name",
};

const OPERATOR_LABELS: Record<string, string> = {
  equals: "is",
  not_equals: "is not",
  in: "is one of",
  has_any: "has any",
  has_all: "has all",
  has_none: "has none",
  contains: "contains",
  starts_with: "starts with",
  gte: ">=",
  lte: "<=",
  gt: ">",
  lt: "<",
  after: "after",
  before: "before",
  is_true: "is true",
  is_false: "is false",
  is_null: "is empty",
  is_not_null: "is not empty",
};

function formatValue(value: FilterRule["value"]): string {
  if (Array.isArray(value)) {
    return value.length <= 2 ? value.join(", ") : `${value.length} items`;
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  return String(value);
}

export function FilterChip({ rule, onRemove }: FilterChipProps) {
  const fieldLabel = FIELD_LABELS[rule.field] ?? rule.field;
  const operatorLabel = OPERATOR_LABELS[rule.operator] ?? rule.operator;
  const showValue = !["is_true", "is_false", "is_null", "is_not_null"].includes(rule.operator);

  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-1 text-xs font-medium">
      <span className="text-muted-foreground">{fieldLabel}</span>
      <span>{operatorLabel}</span>
      {showValue && (
        <span className="font-semibold">{formatValue(rule.value)}</span>
      )}
      <button
        type="button"
        onClick={onRemove}
        className="ml-0.5 rounded-full p-0.5 hover:bg-foreground/10"
      >
        <X className="h-3 w-3" />
      </button>
    </span>
  );
}
