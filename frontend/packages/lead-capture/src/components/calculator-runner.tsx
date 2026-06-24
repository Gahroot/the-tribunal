"use client";

import { useMemo, useState } from "react";

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
import { formatCurrency, formatNumber } from "@/lib/utils/number";
import { evaluateFormula } from "@/lib/utils/safe-formula";
import type { CalculatorContent, CalculatorOutput } from "@/types";

interface CalculatorRunnerProps {
  content: CalculatorContent;
}

function formatOutput(value: number | null, format: CalculatorOutput["format"]): string {
  if (value === null) return "—";
  switch (format) {
    case "currency":
      return formatCurrency(value);
    case "percentage":
      return `${formatNumber(Math.round(value * 100) / 100)}%`;
    case "text":
      return String(value);
    default:
      return formatNumber(Math.round(value * 100) / 100);
  }
}

/**
 * Interactive calculator a prospect can actually use on a public page. Inputs
 * feed a safe arithmetic evaluator (no eval) that resolves calculations and
 * outputs live as the visitor types.
 */
export function CalculatorRunner({ content }: CalculatorRunnerProps) {
  const inputs = content.inputs ?? [];

  const [values, setValues] = useState<Record<string, number>>(() => {
    const initial: Record<string, number> = {};
    for (const input of inputs) {
      if (input.type === "select") {
        const first = input.options?.[0];
        initial[input.id] = first?.multiplier ?? 0;
      } else {
        initial[input.id] = input.default_value ?? 0;
      }
    }
    return initial;
  });

  const outputs = useMemo(() => {
    const scope: Record<string, number> = { ...values };

    for (const calc of content.calculations ?? []) {
      const result = evaluateFormula(calc.formula, scope);
      if (result !== null) scope[calc.id] = result;
    }

    return (content.outputs ?? []).map((output) => ({
      ...output,
      value: evaluateFormula(output.formula, scope),
    }));
  }, [values, content.calculations, content.outputs]);

  if (inputs.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        This calculator has no inputs yet.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      {content.description && (
        <p className="text-sm text-muted-foreground">{content.description}</p>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {inputs.map((input) => (
          <div key={input.id} className="space-y-2">
            <Label htmlFor={input.id}>{input.label}</Label>

            {input.type === "select" ? (
              <Select
                value={String(values[input.id] ?? "")}
                onValueChange={(value) =>
                  setValues((prev) => ({ ...prev, [input.id]: Number(value) }))
                }
              >
                <SelectTrigger id={input.id}>
                  <SelectValue placeholder="Select…" />
                </SelectTrigger>
                <SelectContent>
                  {(input.options ?? []).map((opt) => (
                    <SelectItem
                      key={opt.value}
                      value={String(opt.multiplier ?? 0)}
                    >
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <div className="relative">
                {input.prefix && (
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                    {input.prefix}
                  </span>
                )}
                <Input
                  id={input.id}
                  type="number"
                  placeholder={input.placeholder}
                  className={input.prefix ? "pl-7" : undefined}
                  value={values[input.id] === 0 ? "" : values[input.id]}
                  onChange={(e) =>
                    setValues((prev) => ({
                      ...prev,
                      [input.id]: parseFloat(e.target.value) || 0,
                    }))
                  }
                />
                {input.suffix && (
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-muted-foreground">
                    {input.suffix}
                  </span>
                )}
              </div>
            )}

            {input.help_text && (
              <p className="text-xs text-muted-foreground">{input.help_text}</p>
            )}
          </div>
        ))}
      </div>

      <div className="space-y-3 rounded-lg border bg-muted/40 p-4">
        {outputs.map((output) => (
          <div
            key={output.id}
            className={
              output.highlight
                ? "flex items-center justify-between gap-4"
                : "flex items-center justify-between gap-4 text-sm text-muted-foreground"
            }
          >
            <div>
              <p className={output.highlight ? "font-medium" : ""}>
                {output.label}
              </p>
              {output.description && output.highlight && (
                <p className="text-xs text-muted-foreground">
                  {output.description}
                </p>
              )}
            </div>
            <span
              className={
                output.highlight
                  ? "text-2xl font-bold text-primary"
                  : "font-medium"
              }
            >
              {formatOutput(output.value, output.format)}
            </span>
          </div>
        ))}
      </div>

      {content.cta && (
        <div className="space-y-1">
          <Button type="button">{content.cta.text}</Button>
          {content.cta.description && (
            <p className="text-xs text-muted-foreground">
              {content.cta.description}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
