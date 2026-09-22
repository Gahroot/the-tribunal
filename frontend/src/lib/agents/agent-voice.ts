import {
  REALTIME_VOICES,
  HUME_VOICES,
  GROK_VOICES,
  ELEVENLABS_VOICES,
  type VoiceOption,
} from "@/lib/voice-constants";

/**
 * Single source of truth for agent voice provider / voice resolution shared by
 * the create wizard and the edit screen.
 */

export type VoiceProvider = "openai" | "hume" | "grok" | "elevenlabs";

export const DEFAULT_VOICE_BY_PROVIDER: Record<VoiceProvider, string> = {
  openai: "marin",
  hume: "kora",
  grok: "ara",
  elevenlabs: "ava",
};

/**
 * Map a pricing tier id to the underlying voice provider used by the API.
 * Unknown tiers fall back to OpenAI Realtime.
 */
export function getVoiceProviderForTier(tier: string): VoiceProvider {
  switch (tier) {
    case "grok":
      return "grok";
    case "openai-hume":
      return "hume";
    case "elevenlabs":
      return "elevenlabs";
    default:
      return "openai";
  }
}

/**
 * Selectable OpenAI Realtime models for the agent edit screen. Kept in sync
 * with the backend registry (SUPPORTED_REALTIME_MODELS). The gpt-realtime-2.x
 * models power the "GPT Live" experience (full-duplex + reasoning delegation).
 */
export const REALTIME_MODEL_OPTIONS: { id: string; label: string; description: string }[] = [
  {
    id: "gpt-realtime-2.1",
    label: "GPT Live (Realtime 2.1)",
    description: "Full-duplex + background reasoning, best quality",
  },
  {
    id: "gpt-realtime-2.1-mini",
    label: "GPT Live Mini (Realtime 2.1 mini)",
    description: "Reasoning + tools at lower cost",
  },
  {
    id: "gpt-realtime-2",
    label: "Realtime 2",
    description: "Previous reasoning voice model",
  },
  {
    id: "gpt-realtime",
    label: "Realtime",
    description: "Non-reasoning, lowest latency",
  },
  {
    id: "gpt-realtime-mini",
    label: "Realtime mini",
    description: "Non-reasoning, cheapest",
  },
];

/** Sentinel Select value representing "use the workspace default model" (null). */
export const REALTIME_MODEL_DEFAULT_VALUE = "default";

/**
 * Map a pricing tier id to the OpenAI Realtime model persisted on the agent.
 * Returns null for tiers that use the global default model or a non-OpenAI
 * provider, so the backend falls back to settings.openai_realtime_model.
 */
export function getRealtimeModelForTier(tier: string): string | null {
  switch (tier) {
    case "gpt-live":
      return "gpt-realtime-2.1";
    case "gpt-live-mini":
      return "gpt-realtime-2.1-mini";
    case "premium":
      return "gpt-realtime";
    case "premium-mini":
      return "gpt-realtime-mini";
    default:
      return null;
  }
}

/** Return the selectable voices for a given provider. */
export function getVoicesForProvider(provider: string): VoiceOption[] {
  switch (provider) {
    case "grok":
      return GROK_VOICES;
    case "hume":
      return HUME_VOICES;
    case "elevenlabs":
      return ELEVENLABS_VOICES;
    default:
      return REALTIME_VOICES;
  }
}

/** Return the recommended default voice id for a provider. */
export function getDefaultVoiceForProvider(provider: string): string {
  return DEFAULT_VOICE_BY_PROVIDER[provider as VoiceProvider] ?? DEFAULT_VOICE_BY_PROVIDER.openai;
}

/**
 * Resolve a valid voice id for the given provider: keep the current voice when
 * it is valid for the provider, otherwise fall back to the provider default.
 */
export function resolveVoiceForProvider(provider: string, currentVoice: string): string {
  const validIds = getVoicesForProvider(provider).map((v) => v.id);
  return validIds.includes(currentVoice) ? currentVoice : getDefaultVoiceForProvider(provider);
}
