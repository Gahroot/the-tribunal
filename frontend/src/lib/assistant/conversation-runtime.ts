/**
 * Pure conversation-runtime logic for the CRM assistant chat.
 *
 * This module owns the streaming state machine and message parsing so the
 * presentational chat components and the `useAssistantChat` container hook can
 * stay thin and the transitions can be unit tested in isolation.
 */

import type {
  AssistantMessageResponse,
  AssistantStreamEvent,
} from "@/lib/api/assistant";

export interface RuntimeTool {
  name: string;
  status: "running" | "complete";
  success?: boolean | null;
}

export interface ConversationRuntime {
  messages: AssistantMessageResponse[];
  streamingText: string;
  reasoningText: string;
  activeTools: RuntimeTool[];
  completedTools: RuntimeTool[];
  isStreaming: boolean;
  error: string | null;
  retryNotice: string | null;
  requestId: string | null;
}

export interface StreamAccumulator {
  text: string;
  reasoning: string;
  activeTools: RuntimeTool[];
  completedTools: RuntimeTool[];
}

/**
 * Result of folding a single stream event into the running state.
 *
 * `patch` is merged into the existing runtime (preserving prior messages),
 * `appendMessage` is appended to `runtime.messages` only on completion, and
 * `finished` signals the caller to tear down per-conversation stream refs.
 */
export interface StreamEventResult {
  accumulator: StreamAccumulator;
  patch: Partial<ConversationRuntime>;
  appendMessage: AssistantMessageResponse | null;
  finished: boolean;
}

export function emptyRuntime(): ConversationRuntime {
  return {
    messages: [],
    streamingText: "",
    reasoningText: "",
    activeTools: [],
    completedTools: [],
    isStreaming: false,
    error: null,
    retryNotice: null,
    requestId: null,
  };
}

export function emptyAccumulator(): StreamAccumulator {
  return { text: "", reasoning: "", activeTools: [], completedTools: [] };
}

export function createRuntimeId(): string {
  return crypto.randomUUID();
}

/**
 * Resolve which conversation id is active given the explicit selection, the
 * loaded conversation list, and the current draft id. Falls back to the first
 * persisted conversation, then the draft, so a freshly mounted chat always has
 * a stable target before the user picks anything.
 */
export function resolveActiveConversationId(
  activeConversationId: string | null,
  conversations: { id: string }[],
  draftConversationId: string,
): string {
  return activeConversationId ?? conversations[0]?.id ?? draftConversationId;
}

/**
 * Pick the runtime to render for the active conversation. A stored runtime wins
 * once it is streaming, already has messages, or belongs to the in-progress
 * draft; otherwise hydrate from the persisted conversation messages when they
 * match, falling back to an empty runtime.
 */
export function resolveActiveRuntime(params: {
  storedRuntime: ConversationRuntime | undefined;
  isDraftActive: boolean;
  hydratedMessages: AssistantMessageResponse[] | null;
}): ConversationRuntime {
  const { storedRuntime, isDraftActive, hydratedMessages } = params;
  if (storedRuntime?.isStreaming || storedRuntime?.messages.length || isDraftActive) {
    return storedRuntime ?? emptyRuntime();
  }
  if (hydratedMessages) {
    return { ...emptyRuntime(), messages: hydratedMessages };
  }
  return storedRuntime ?? emptyRuntime();
}

/** Messages shown in the transcript: tool-role messages are internal and hidden. */
export function selectVisibleMessages(
  messages: AssistantMessageResponse[],
): AssistantMessageResponse[] {
  return messages.filter((message) => message.role !== "tool");
}

/** Shallow-merge a runtime patch onto an existing (or empty) runtime. */
export function mergeRuntimePatch(
  runtime: ConversationRuntime | undefined,
  patch: Partial<ConversationRuntime>,
): ConversationRuntime {
  return { ...(runtime ?? emptyRuntime()), ...patch };
}

/**
 * Reset the runtime for a new user turn: append the user message and clear the
 * streaming/tool/error fields so a fresh assistant response can accumulate.
 */
export function startUserTurn(
  runtime: ConversationRuntime,
  userMessage: AssistantMessageResponse,
  requestId: string,
): ConversationRuntime {
  return {
    ...runtime,
    messages: [...runtime.messages, userMessage],
    streamingText: "",
    reasoningText: "",
    activeTools: [],
    completedTools: [],
    isStreaming: true,
    error: null,
    retryNotice: null,
    requestId,
  };
}

/**
 * Apply a finished {@link StreamEventResult} to a runtime: merge the patch and
 * append the completed assistant message when one was produced.
 */
export function applyStreamResult(
  runtime: ConversationRuntime,
  result: StreamEventResult,
): ConversationRuntime {
  return {
    ...runtime,
    ...result.patch,
    messages: result.appendMessage
      ? [...runtime.messages, result.appendMessage]
      : runtime.messages,
  };
}

/**
 * Fold a single SSE event into the accumulator and produce the runtime patch.
 *
 * The function is pure: it never mutates the input accumulator and returns the
 * next accumulator plus the runtime patch the caller should apply. `now` is
 * injectable so completion timestamps/ids stay deterministic under test.
 */
export function reduceStreamEvent(
  accumulator: StreamAccumulator,
  event: AssistantStreamEvent,
  now: () => Date = () => new Date(),
): StreamEventResult {
  switch (event.type) {
    case "delta": {
      const nextAccumulator = { ...accumulator, text: accumulator.text + event.text };
      return {
        accumulator: nextAccumulator,
        patch: { streamingText: nextAccumulator.text },
        appendMessage: null,
        finished: false,
      };
    }

    case "reasoning": {
      const nextAccumulator = {
        ...accumulator,
        reasoning: accumulator.reasoning + event.text,
      };
      return {
        accumulator: nextAccumulator,
        patch: { reasoningText: nextAccumulator.reasoning },
        appendMessage: null,
        finished: false,
      };
    }

    case "tool_start": {
      const activeTools: RuntimeTool[] = [
        ...accumulator.activeTools.filter((tool) => tool.name !== event.name),
        { name: event.name, status: "running" },
      ];
      const nextAccumulator = { ...accumulator, activeTools };
      return {
        accumulator: nextAccumulator,
        patch: { activeTools },
        appendMessage: null,
        finished: false,
      };
    }

    case "tool_end": {
      const activeTools = accumulator.activeTools.filter(
        (tool) => tool.name !== event.name,
      );
      const completedTools: RuntimeTool[] = [
        ...accumulator.completedTools,
        { name: event.name, status: "complete", success: event.success },
      ];
      const nextAccumulator = { ...accumulator, activeTools, completedTools };
      return {
        accumulator: nextAccumulator,
        patch: { activeTools, completedTools },
        appendMessage: null,
        finished: false,
      };
    }

    case "retry":
      return {
        accumulator,
        patch: {
          retryNotice: `Retrying ${event.reason.replaceAll("_", " ")} (${event.attempt})`,
        },
        appendMessage: null,
        finished: false,
      };

    case "error":
      return {
        accumulator,
        patch: { isStreaming: false, error: event.message, requestId: null },
        appendMessage: null,
        finished: false,
      };

    case "done": {
      const timestamp = now();
      const appendMessage: AssistantMessageResponse | null = accumulator.text
        ? {
            id:
              event.message_id ??
              `assistant-${event.conversation_id}-${timestamp.getTime()}`,
            role: "assistant",
            content: accumulator.text,
            tool_calls: accumulator.completedTools.map((tool, index) => ({
              id: `tool-${index}`,
              function: { name: tool.name, arguments: "{}" },
            })),
            created_at: timestamp.toISOString(),
          }
        : null;
      return {
        accumulator,
        patch: {
          streamingText: "",
          reasoningText: "",
          activeTools: [],
          completedTools: accumulator.completedTools,
          isStreaming: false,
          error: null,
          retryNotice: null,
          requestId: null,
        },
        appendMessage,
        finished: true,
      };
    }
  }
}

export function toolNamesFromMessage(message: AssistantMessageResponse): string[] {
  return (message.tool_calls ?? [])
    .map((toolCall) => toolCall.function?.name)
    .filter((name): name is string => Boolean(name));
}

export function parseWorkflowPayload(
  content: string,
): Record<string, unknown> | null {
  if (!content.trim().startsWith("{")) return null;

  try {
    const parsed: unknown = JSON.parse(content);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;

    const record = parsed as Record<string, unknown>;
    if (
      record.type === "outbound_workflow" ||
      record.outbound_workflow === true ||
      record.segment_preview ||
      record.message_previews ||
      record.launch_status ||
      record.warm_lead_handoff
    ) {
      return record;
    }
  } catch {
    return null;
  }

  return null;
}
