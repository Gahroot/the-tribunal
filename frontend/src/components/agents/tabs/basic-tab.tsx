import type { UseFormReturn } from "react-hook-form";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Phone, MessageSquare, MessagesSquare } from "lucide-react";
import type { EditAgentFormValues } from "@/components/agents/agent-edit-schema";

interface BasicTabProps {
  form: UseFormReturn<EditAgentFormValues>;
  availableLanguages: Array<{ code: string; name: string }>;
}

export function BasicTab({ form, availableLanguages }: BasicTabProps) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium">Basic Information</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-3 md:grid-cols-2">
          <FormField
            control={form.control}
            name="name"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Agent Name</FormLabel>
                <FormControl>
                  <Input placeholder="Customer Support Agent" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="language"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Language</FormLabel>
                <Select onValueChange={field.onChange} value={field.value}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select a language" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent className="max-h-[300px]">
                    {availableLanguages.map((lang) => (
                      <SelectItem key={lang.code} value={lang.code}>
                        {lang.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <FormField
          control={form.control}
          name="description"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Description</FormLabel>
              <FormControl>
                <Textarea
                  placeholder="Handles customer inquiries and support"
                  className="min-h-[80px]"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="channelMode"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Channel Mode</FormLabel>
              <FormDescription>
                Select which communication channels this agent supports
              </FormDescription>
              <div className="grid grid-cols-3 gap-3 pt-2">
                {[
                  {
                    value: "voice",
                    label: "Voice Only",
                    description: "Phone calls only",
                    icon: Phone,
                  },
                  {
                    value: "text",
                    label: "Text Only",
                    description: "SMS/text messages only",
                    icon: MessageSquare,
                  },
                  {
                    value: "both",
                    label: "Voice & Text",
                    description: "Both channels",
                    icon: MessagesSquare,
                  },
                ].map((option) => {
                  const Icon = option.icon;
                  const isSelected = field.value === option.value;
                  return (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => field.onChange(option.value)}
                      className={`flex flex-col items-center gap-2 rounded-lg border-2 p-4 text-center transition-colors ${
                        isSelected
                          ? "border-primary bg-primary/5"
                          : "border-border hover:border-primary/50"
                      }`}
                    >
                      <Icon
                        className={`h-6 w-6 ${isSelected ? "text-primary" : "text-muted-foreground"}`}
                      />
                      <div>
                        <p
                          className={`text-sm font-medium ${isSelected ? "text-primary" : ""}`}
                        >
                          {option.label}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {option.description}
                        </p>
                      </div>
                    </button>
                  );
                })}
              </div>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="isActive"
          render={({ field }) => (
            <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
              <div className="space-y-0.5">
                <FormLabel className="text-base">Active Status</FormLabel>
                <FormDescription>Enable or disable this agent</FormDescription>
              </div>
              <FormControl>
                <Switch checked={field.value} onCheckedChange={field.onChange} />
              </FormControl>
            </FormItem>
          )}
        />
      </CardContent>
    </Card>
  );
}
