import { describe, expect, it } from "vitest";

import type { AssistantStreamEvent } from "@/lib/api/assistant";

import {
  emptyAccumulator,
  emptyRuntime,
  parseWorkflowPayload,
  reduceStreamEvent,
  toolNamesFromMessage,
  type ConversationRuntime,
  type StreamAccumulator,
} from "./conversation-runtime";

const FIXED_NOW = () => new Date("2026-05-20T14:00:00.000Z");

/** Fold a list of events through the reducer, returning the final accumulator + merged runtime. */
function runEvents(events: AssistantStreamEvent[]): {
  accumulator: StreamAccumulator;
  runtime: ConversationRuntime;
  appended: ConversationRuntime["messages"];
} {
  let accumulator = emptyAccumulator();
  let runtime = emptyRuntime();
  const appended: ConversationRuntime["messages"] = [];

  for (const event of events) {
    const result = reduceStreamEvent(accumulator, event, FIXED_NOW);
    accumulator = result.accumulator;
    runtime = { ...runtime, ...result.patch };
    if (result.appendMessage) {
      appended.push(result.appendMessage);
      runtime = { ...runtime, messages: [...runtime.messages, result.appendMessage] };
    }
  }

  return { accumulator, runtime, appended };
}

describe("reduceStreamEvent", () => {
  it("appends delta text without mutating the input accumulator", () => {
    const accumulator = emptyAccumulator();
    const result = reduceStreamEvent(accumulator, { type: "delta", text: "Hello" }, FIXED_NOW);

    expect(result.accumulator.text).toBe("Hello");
    expect(result.patch).toEqual({ streamingText: "Hello" });
    expect(result.finished).toBe(false);
    // input accumulator is untouched (purity)
    expect(accumulator.text).toBe("");
  });

  it("accumulates consecutive deltas and reasoning separately", () => {
    const { accumulator, runtime } = runEvents([
      { type: "delta", text: "Found " },
      { type: "reasoning", text: "Checking leads" },
      { type: "delta", text: "12 leads." },
    ]);

    expect(accumulator.text).toBe("Found 12 leads.");
    expect(accumulator.reasoning).toBe("Checking leads");
    expect(runtime.streamingText).toBe("Found 12 leads.");
    expect(runtime.reasoningText).toBe("Checking leads");
  });

  it("moves a tool from active to completed across tool_start/tool_end", () => {
    const startResult = reduceStreamEvent(
      emptyAccumulator(),
      { type: "tool_start", name: "search_contacts" },
      FIXED_NOW,
    );
    expect(startResult.accumulator.activeTools).toEqual([
      { name: "search_contacts", status: "running" },
    ]);

    const endResult = reduceStreamEvent(
      startResult.accumulator,
      { type: "tool_end", name: "search_contacts", success: true },
      FIXED_NOW,
    );
    expect(endResult.accumulator.activeTools).toEqual([]);
    expect(endResult.accumulator.completedTools).toEqual([
      { name: "search_contacts", status: "complete", success: true },
    ]);
  });

  it("deduplicates a repeated tool_start for the same tool name", () => {
    const first = reduceStreamEvent(
      emptyAccumulator(),
      { type: "tool_start", name: "draft_sms" },
      FIXED_NOW,
    );
    const second = reduceStreamEvent(
      first.accumulator,
      { type: "tool_start", name: "draft_sms" },
      FIXED_NOW,
    );

    expect(second.accumulator.activeTools).toEqual([
      { name: "draft_sms", status: "running" },
    ]);
  });

  it("formats a human-readable retry notice", () => {
    const result = reduceStreamEvent(
      emptyAccumulator(),
      { type: "retry", reason: "rate_limited", attempt: 2 },
      FIXED_NOW,
    );

    expect(result.patch.retryNotice).toBe("Retrying rate limited (2)");
    expect(result.finished).toBe(false);
  });

  it("stops streaming and surfaces the message on error", () => {
    const result = reduceStreamEvent(
      emptyAccumulator(),
      { type: "error", message: "stream failed" },
      FIXED_NOW,
    );

    expect(result.patch).toMatchObject({
      isStreaming: false,
      error: "stream failed",
      requestId: null,
    });
  });

  it("builds an assistant message with deterministic id and tool calls on done", () => {
    const { runtime, appended } = runEvents([
      { type: "tool_start", name: "search_contacts" },
      { type: "tool_end", name: "search_contacts", success: true },
      { type: "delta", text: "Done." },
      {
        type: "done",
        conversation_id: "conv_1",
        message_id: null,
        actions_taken: [],
      },
    ]);

    expect(appended).toHaveLength(1);
    const message = appended[0]!;
    expect(message.id).toBe(`assistant-conv_1-${FIXED_NOW().getTime()}`);
    expect(message.content).toBe("Done.");
    expect(message.tool_calls).toEqual([
      { id: "tool-0", function: { name: "search_contacts", arguments: "{}" } },
    ]);
    expect(runtime.isStreaming).toBe(false);
    expect(runtime.streamingText).toBe("");
  });

  it("prefers an explicit message_id when provided on done", () => {
    const { appended } = runEvents([
      { type: "delta", text: "Hi" },
      {
        type: "done",
        conversation_id: "conv_2",
        message_id: "msg_explicit",
        actions_taken: [],
      },
    ]);

    expect(appended[0]!.id).toBe("msg_explicit");
  });

  it("does not append a message on done when no text was streamed", () => {
    const { appended, runtime } = runEvents([
      {
        type: "done",
        conversation_id: "conv_3",
        message_id: "msg_empty",
        actions_taken: [],
      },
    ]);

    expect(appended).toHaveLength(0);
    expect(runtime.messages).toHaveLength(0);
  });
});

describe("toolNamesFromMessage", () => {
  it("extracts tool names and ignores entries without a function name", () => {
    const names = toolNamesFromMessage({
      id: "m1",
      role: "assistant",
      content: "",
      created_at: "2026-05-20T14:00:00Z",
      tool_calls: [
        { id: "t1", function: { name: "search_contacts", arguments: "{}" } },
        { id: "t2", function: { name: "", arguments: "{}" } },
      ],
    });

    expect(names).toEqual(["search_contacts"]);
  });

  it("returns an empty array when there are no tool calls", () => {
    const names = toolNamesFromMessage({
      id: "m2",
      role: "assistant",
      content: "no tools",
      created_at: "2026-05-20T14:00:00Z",
    });

    expect(names).toEqual([]);
  });
});

describe("parseWorkflowPayload", () => {
  it("returns the record for a tagged outbound workflow payload", () => {
    const payload = parseWorkflowPayload(
      JSON.stringify({ type: "outbound_workflow", title: "Ready" }),
    );
    expect(payload).toMatchObject({ type: "outbound_workflow", title: "Ready" });
  });

  it("recognizes alternate workflow markers", () => {
    expect(parseWorkflowPayload(JSON.stringify({ message_previews: [] }))).not.toBeNull();
    expect(parseWorkflowPayload(JSON.stringify({ launch_status: "running" }))).not.toBeNull();
    expect(parseWorkflowPayload(JSON.stringify({ warm_lead_handoff: {} }))).not.toBeNull();
  });

  it("returns null for plain text, arrays, and untagged objects", () => {
    expect(parseWorkflowPayload("just a normal reply")).toBeNull();
    expect(parseWorkflowPayload(JSON.stringify([1, 2, 3]))).toBeNull();
    expect(parseWorkflowPayload(JSON.stringify({ greeting: "hi" }))).toBeNull();
  });

  it("returns null for malformed JSON that starts with a brace", () => {
    expect(parseWorkflowPayload("{ not valid json")).toBeNull();
  });
});
