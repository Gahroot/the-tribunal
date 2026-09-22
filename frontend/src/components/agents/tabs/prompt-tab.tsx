"use client";

import {
  Check,
  FlaskConical,
  History,
  Loader2,
  PlayCircle,
  RefreshCw,
  Sparkles,
  X,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { type UseFormReturn } from "react-hook-form";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import type { EditAgentFormValues } from "@/lib/agents/agent-form";
import { assistantApi } from "@/lib/api/assistant";
import { messages } from "@/lib/messages";
import { getApiErrorMessage } from "@/lib/utils/errors";
import { BEST_PRACTICES_PROMPT } from "@/lib/voice-constants";

/**
 * Tool calls that mutate CRM records. If the assistant runs one of these
 * instead of just rewriting the prompt, we refuse to show its reply as a
 * suggestion — the human accept/reject flow must stay the only write path.
 */
const WRITE_TOOL_PATTERN =
  /^(create|update|delete|send|start|pause|resume|assign|plan|mark|close)/;

/** Known backend fallback strings — not usable prompt suggestions. */
const ASSISTANT_FAILURE_RESPONSES = new Set([
  "Sorry, that took too long. Please try again.",
  "Something went wrong processing your request. Please try again.",
]);

/**
 * Build the assistant request for the "Improve with AI" action.
 * Explicit about output shape and about staying a pure writing task so the
 * reply is insertable text rather than a tool-driven CRM mutation.
 */
function buildImproveMessage(currentPrompt: string): string {
  const source =
    currentPrompt.trim() || "(The prompt is empty — write a strong starting prompt.)";
  return [
    "Improve the system prompt below for an AI phone agent.",
    "",
    "Rules:",
    "- Keep the agent's role, language, and intent; keep markdown structure where it helps.",
    "- Make every instruction clearer, more specific, and easier to follow on a live call.",
    "- Keep the whole prompt under 1,600 characters.",
    "- Do not call any tools and do not modify any records — this is a writing task only.",
    "- Reply with ONLY the improved prompt text: no preamble, no explanation,",
    "  no markdown code fences, no surrounding quotes.",
    "",
    "Current prompt:",
    "---",
    source,
    "---",
  ].join("\n");
}

/**
 * Normalize an assistant reply into insertable prompt text.
 * Returns "" when the reply is empty or a known backend failure string.
 */
function extractSuggestionText(raw: string | null | undefined): string {
  if (!raw) return "";
  let text = raw.trim();
  if (!text || ASSISTANT_FAILURE_RESPONSES.has(text)) return "";

  // Fully fenced reply → keep the body, drop the fences.
  const fenced = text.match(/^```[a-zA-Z0-9_-]*\s*\n([\s\S]*?)\n?```\s*$/);
  if (fenced) return fenced[1].trim();

  // Partially fenced output → strip fence marker lines.
  text = text.replace(/^\s*```[a-zA-Z0-9_-]*\s*$/gm, "").trim();

  // Drop a short lead-in line like "Here's the improved prompt:".
  const lines = text.split("\n");
  if (lines.length > 1) {
    const first = lines[0].trim();
    if (first.endsWith(":") && first.split(/\s+/).length <= 10) {
      text = lines.slice(1).join("\n").trim();
    }
  }

  // Unwrap fully quoted output.
  if (text.length >= 2) {
    const quote = text[0];
    if ((quote === '"' || quote === "'" || quote === "`") && text.endsWith(quote)) {
      text = text.slice(1, -1).trim();
    }
  }

  return text;
}

interface PromptTabProps {
  form: UseFormReturn<EditAgentFormValues>;
  /** Enables the "Test in Practice Arena" link (needs a saved agent id). */
  agentId?: string | null;
  /** Reveals the folded prompt-version history section below the editor. */
  onShowVersions?: () => void;
  /** Reveals the folded A/B testing section below the editor. */
  onShowTests?: () => void;
}

export function PromptTab({ form, agentId, onShowVersions, onShowTests }: PromptTabProps) {
  const workspaceId = useWorkspaceId();
  const [isImproving, setIsImproving] = useState(false);
  const [suggestion, setSuggestion] = useState<string | null>(null);

  const promptValue = form.watch("systemPrompt") ?? "";
  const promptLength = promptValue.length;
  const hasValue = promptLength > 0;
  const lengthOptimal = promptLength >= 100 && promptLength <= 2000;
  const promptDirty = Boolean(form.formState.dirtyFields.systemPrompt);

  /**
   * Ask the existing CRM assistant endpoint to rewrite the current draft.
   * The reply never writes anything itself — it lands in `suggestion` for the
   * human to insert or discard below.
   */
  async function handleImprove(): Promise<void> {
    if (isImproving) return;
    if (!workspaceId) {
      toast.error(messages.workspace.notLoaded);
      return;
    }
    setIsImproving(true);
    try {
      const result = await assistantApi.chat(
        workspaceId,
        buildImproveMessage(form.getValues("systemPrompt"))
      );
      const writeTool = (result.actions_taken ?? []).find((action) =>
        WRITE_TOOL_PATTERN.test(action.tool_name)
      );
      if (writeTool) {
        toast.error(messages.agents.promptImproveTookAction);
        return;
      }
      const text = extractSuggestionText(result.response);
      if (!text) {
        toast.error(messages.agents.promptImproveFailed);
        return;
      }
      setSuggestion(text);
    } catch (err) {
      toast.error(getApiErrorMessage(err, messages.agents.promptImproveFailed));
    } finally {
      setIsImproving(false);
    }
  }

  /** Accept: replace the draft with the suggestion (marks the form dirty). */
  function handleInsertSuggestion(): void {
    if (!suggestion) return;
    form.setValue("systemPrompt", suggestion, { shouldDirty: true });
    setSuggestion(null);
    toast.success(messages.agents.promptSuggestionInserted);
  }

  /** Reset: discard unsaved prompt edits and restore the last saved version. */
  function handleResetPrompt(): void {
    form.resetField("systemPrompt");
    toast.success(messages.agents.promptReset);
  }

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-lg">AI Configuration</CardTitle>
          <CardDescription>System prompt, testing, and version control</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Best-practices helper banner */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed border-muted-foreground/30 bg-muted/30 px-4 py-3">
            <p className="text-sm text-muted-foreground">
              Need help writing a prompt? Start with our best practices template.
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => form.setValue("systemPrompt", BEST_PRACTICES_PROMPT, { shouldDirty: true })}
            >
              Use Best Practices
            </Button>
          </div>

          {/* AI suggestion: generate → review → insert or discard */}
          {suggestion && (
            <div className="rounded-lg border border-primary/30 bg-primary/5 p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <p className="flex items-center gap-1.5 text-sm font-medium">
                  <Sparkles className="size-4 text-primary" aria-hidden="true" />
                  AI suggestion
                  <span className="text-xs font-normal text-muted-foreground">
                    review before inserting
                  </span>
                </p>
                <div className="flex items-center gap-1.5">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 gap-1 px-2 text-xs"
                    onClick={() => void handleImprove()}
                    disabled={isImproving}
                  >
                    {isImproving ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="size-3.5" />
                    )}
                    Regenerate
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-7 gap-1 px-2 text-xs"
                    onClick={() => setSuggestion(null)}
                  >
                    <X className="size-3.5" />
                    Discard
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    className="h-7 gap-1 px-2 text-xs"
                    onClick={handleInsertSuggestion}
                  >
                    <Check className="size-3.5" />
                    Insert
                  </Button>
                </div>
              </div>
              <div className="max-h-64 overflow-auto rounded-md border bg-background p-3">
                <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed">
                  {suggestion}
                </pre>
              </div>
            </div>
          )}

          <FormField
            control={form.control}
            name="systemPrompt"
            render={({ field }) => (
              <FormItem>
                {/* Monospace prompt editor: header (label + actions), editing
                    surface, status bar (count · reset · practice) */}
                <div className="overflow-hidden rounded-lg border bg-card shadow-xs transition-colors focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/20">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-muted/40 px-3 py-2">
                    <FormLabel className="text-xs font-medium text-muted-foreground">
                      System Prompt
                    </FormLabel>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {onShowVersions && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-7 gap-1 px-2 text-xs"
                          onClick={onShowVersions}
                        >
                          <History className="size-3.5" />
                          Versions
                        </Button>
                      )}
                      {onShowTests && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          className="h-7 gap-1 px-2 text-xs"
                          onClick={onShowTests}
                        >
                          <FlaskConical className="size-3.5" />
                          A/B Test
                        </Button>
                      )}
                      <Button
                        type="button"
                        size="sm"
                        className="h-7 gap-1 px-2 text-xs"
                        onClick={() => void handleImprove()}
                        disabled={isImproving}
                      >
                        {isImproving ? (
                          <Loader2 className="size-3.5 animate-spin" />
                        ) : (
                          <Sparkles className="size-3.5" />
                        )}
                        {isImproving ? "Improving..." : "Improve with AI"}
                      </Button>
                    </div>
                  </div>

                  <FormControl>
                    <Textarea
                      placeholder="Example: You are a friendly appointment setter for a dental clinic..."
                      className="min-h-[240px] resize-y rounded-none border-0 bg-background px-3 py-3 font-mono text-sm leading-relaxed shadow-none focus-visible:ring-0"
                      {...field}
                    />
                  </FormControl>

                  <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t bg-muted/40 px-3 py-1.5">
                    <p className="text-xs text-muted-foreground">
                      {hasValue ? `${promptLength} characters` : "No characters"}
                      <span aria-hidden="true"> · </span>
                      <span
                        className={
                          lengthOptimal ? "text-emerald-600 dark:text-emerald-400" : ""
                        }
                      >
                        {lengthOptimal ? "optimal" : "recommended: under 2,000"}
                      </span>
                    </p>
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={handleResetPrompt}
                        disabled={!promptDirty}
                        title="Restore the last saved prompt"
                        className="text-xs text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:text-muted-foreground disabled:hover:no-underline"
                      >
                        Reset to default
                      </button>
                      {agentId && (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-6 gap-1 px-2 text-xs"
                          asChild
                        >
                          <Link href={`/agents/practice?agentId=${agentId}`}>
                            <PlayCircle className="size-3.5" />
                            Test in Practice Arena
                          </Link>
                        </Button>
                      )}
                    </div>
                  </div>
                </div>

                <FormDescription>
                  How the agent talks on calls. This is its operating brain.
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* Temperature */}
          <FormField
            control={form.control}
            name="temperature"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Temperature</FormLabel>
                <FormControl>
                  <Slider
                    min={0}
                    max={1}
                    step={0.05}
                    value={[field.value]}
                    onValueChange={(vals) => field.onChange(vals[0])}
                  />
                </FormControl>
                <FormDescription>
                  {field.value < 0.3
                    ? "More focused and predictable (0.0-0.3)"
                    : field.value < 0.7
                      ? "Balanced (0.4-0.6)"
                      : "More creative and varied (0.7-1.0)"}
                </FormDescription>
                <FormMessage />
              </FormItem>
            )}
          />
        </CardContent>
      </Card>
    </div>
  );
}
