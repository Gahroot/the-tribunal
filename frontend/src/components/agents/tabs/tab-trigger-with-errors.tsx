import type { UseFormReturn } from "react-hook-form";
import { TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import type { EditAgentFormValues } from "@/components/agents/agent-edit-schema";
import { TAB_FIELDS } from "@/components/agents/agent-edit-schema";

interface TabTriggerWithErrorsProps {
  value: string;
  label: string;
  form: UseFormReturn<EditAgentFormValues>;
}

export function TabTriggerWithErrors({ value, label, form }: TabTriggerWithErrorsProps) {
  const fields = TAB_FIELDS[value] ?? [];
  const errors = form.formState.errors;
  const errorCount = fields.filter((field) => field in errors).length;

  return (
    <TabsTrigger
      value={value}
      className={cn(errorCount > 0 && "text-destructive")}
    >
      {label}
      {errorCount > 0 && (
        <span className="ml-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-destructive text-[10px] font-medium text-destructive-foreground">
          {errorCount}
        </span>
      )}
    </TabsTrigger>
  );
}
