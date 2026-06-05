import { type Control, useWatch } from "react-hook-form";

import type { EditAgentFormValues } from "@/components/agents/agent-edit-schema";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

interface TransferSectionProps {
  control: Control<EditAgentFormValues>;
}

const BRIEFING_PLACEHOLDER =
  "Connecting you to {caller_name}. They want {intent}. {summary}";

const BRIEFING_VARIABLES = [
  { name: "{caller_name}", description: "The caller's name" },
  { name: "{intent}", description: "What the caller wants (from the AI)" },
  { name: "{summary}", description: "Short context summary (from the AI)" },
];

export function TransferSection({ control }: TransferSectionProps) {
  const transferDestination =
    useWatch({ control, name: "transferDestinationNumber" }) ?? "";
  const transferMode = useWatch({ control, name: "transferMode" });
  const hasDestination = transferDestination.trim().length > 0;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium">Live Human Transfer</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          When a caller asks for a human or qualifies as a hot lead, the AI can hand
          the live call to a human closer. Enable the &ldquo;Transfer Call&rdquo;
          tool under the Tools tab, then set the destination here.
        </p>

        <FormField
          control={control}
          name="transferDestinationNumber"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Transfer Destination Number</FormLabel>
              <FormControl>
                <Input
                  type="tel"
                  placeholder="+15551234567"
                  value={field.value ?? ""}
                  onChange={(e) => field.onChange(e.target.value || null)}
                />
              </FormControl>
              <FormDescription>
                E.164 phone number of the human closer. Leave blank to fall back to
                the workspace-level transfer number. With no number configured, the
                AI cannot transfer and will keep handling the call itself.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={control}
          name="transferMode"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Transfer Mode</FormLabel>
              <Select onValueChange={field.onChange} value={field.value}>
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder="Select transfer mode" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  <SelectItem value="warm">
                    Warm — brief the human first, then connect
                  </SelectItem>
                  <SelectItem value="cold">
                    Cold — connect immediately
                  </SelectItem>
                </SelectContent>
              </Select>
              <FormDescription>
                Warm transfers speak a 1&ndash;2 sentence briefing (caller name,
                intent, key facts) to the human before bridging the caller in. Cold
                transfers connect the caller to the human right away.
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        {transferMode === "warm" && (
          <FormField
            control={control}
            name="transferBriefingTemplate"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Briefing Template</FormLabel>
                <FormControl>
                  <Textarea
                    placeholder={BRIEFING_PLACEHOLDER}
                    className="min-h-[80px] font-mono text-sm resize-none"
                    value={field.value ?? ""}
                    onChange={(e) => field.onChange(e.target.value || null)}
                    disabled={!hasDestination}
                  />
                </FormControl>
                <FormDescription>
                  Spoken to the human closer before the caller is connected. Leave
                  blank to use an auto-generated briefing.
                </FormDescription>
                <FormMessage />

                <div className="rounded-md border bg-muted/30 p-3 space-y-1.5">
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                    Available variables
                  </p>
                  <div className="grid gap-1">
                    {BRIEFING_VARIABLES.map((v) => (
                      <div key={v.name} className="flex items-baseline gap-2">
                        <code className="text-xs font-mono bg-background border rounded px-1 py-0.5 text-foreground shrink-0">
                          {v.name}
                        </code>
                        <span className="text-xs text-muted-foreground">
                          {v.description}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </FormItem>
            )}
          />
        )}
      </CardContent>
    </Card>
  );
}
