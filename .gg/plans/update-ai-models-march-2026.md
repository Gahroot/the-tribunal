# Plan: Update AI Models to Latest (March 2026)

## Overview
Update all AI model references across the codebase to use the latest available models as of March 24, 2026. This covers OpenAI text/voice models, xAI Grok voice configurations, ElevenLabs TTS models, and frontend voice/pricing references.

---

## Task 1: Update OpenAI Text Models (gpt-4o → gpt-5.4 family)

**Goal:** Replace all `gpt-4o-mini` references with `gpt-5.4-nano` (cheaper, faster, better for lightweight tasks), and `gpt-4o` with `gpt-5.4-mini` (heavier tasks).

**Files to change:**

### Replace `gpt-4o-mini` → `gpt-5.4-nano` (lightweight tasks):
- `backend/app/services/ai/lead_magnet_generator.py` — lines 160, 302
- `backend/app/services/ai/offer_generator.py` — line 186
- `backend/app/services/ai/opt_out_detector.py` — line 145
- `backend/app/services/ai/qualification.py` — line 154
- `backend/app/services/ai/text_response_generator.py` — lines 220, 306, 417
- `backend/app/services/campaigns/ai_fallback.py` — line 110
- `backend/app/services/scraping/ai_content_analyzer.py` — line 132
- `backend/app/services/ai/testing/__init__.py` — line 25 (comment/example only)
- `backend/app/services/ai/testing/ivr_test_harness.py` — line 11 (comment/example only)
- `backend/app/services/ai/testing/ivr_test_llm.py` — lines 9, 63, 71
- `backend/app/api/v1/embed.py` — line 336 (chat endpoint)

### Replace `gpt-4o` → `gpt-5.4-mini` (heavier tasks needing more intelligence):
- `backend/app/services/ai/campaign_report_service.py` — line 405
- `backend/app/services/ai/prompt_improvement_service.py` — lines 144, 259

**Verification:** `cd backend && uv run ruff check app && uv run mypy app`

---

## Task 2: Fix Deprecated Realtime Model in Embed API

**Goal:** Replace deprecated `gpt-4o-realtime-preview` with `gpt-realtime` in the embed API.

**Files to change:**
- `backend/app/api/v1/embed.py`:
  - Line 236: Change `"model": "gpt-4o-realtime-preview"` → `"model": "gpt-realtime"`
  - Line 287: Change `model="gpt-4o-realtime-preview"` → `model="gpt-realtime"`

**Verification:** `cd backend && uv run ruff check app && uv run mypy app`

---

## Task 3: Update OpenAI Realtime Voice List (Frontend)

**Goal:** Fix the OpenAI Realtime voices list to match the actual supported voices. Per OpenAI docs, the Realtime API supports: alloy, ash, ballad, coral, echo, sage, shimmer, verse, marin, cedar. The voices `fable`, `onyx`, and `nova` are NOT supported by realtime models.

**Files to change:**
- `frontend/src/lib/voice-constants.ts`:
  - Remove `fable`, `nova`, and `onyx` from `REALTIME_VOICES` array (lines 17-19 approx)
  - These voices work in TTS-only models (tts-1, tts-1-hd) but NOT in Realtime API

**Verification:** `cd frontend && npm run lint && npm run build`

---

## Task 4: Update ElevenLabs Model + Add v3 Conversational Option

**Goal:** Add `eleven_v3_conversational` as an available model option for ElevenLabs agents, while keeping `eleven_flash_v2_5` as the default for telephony (it's still the best latency option at 75ms).

**Files to change:**

### Backend:
- `backend/app/services/ai/elevenlabs_tts.py`:
  - Add a class constant for the v3 conversational model: `V3_CONVERSATIONAL_MODEL_ID = "eleven_v3_conversational"`
  - Add a `model_id` parameter to `__init__` so callers can optionally select the model
  - Default remains `eleven_flash_v2_5` for telephony use

### Frontend:
- `frontend/src/lib/pricing-tiers.ts`:
  - Line 74: Update the ElevenLabs tier config `ttsModel` to note v3 availability
  - Add a comment about available models: `eleven_flash_v2_5` (low-latency default), `eleven_v3_conversational` (most expressive)

**Verification:** `cd backend && uv run ruff check app && uv run mypy app` and `cd frontend && npm run lint && npm run build`

---

## Task 5: Update Frontend Pricing Tiers & Model References

**Goal:** Update the pricing tiers to reflect latest model names and capabilities.

**Files to change:**
- `frontend/src/lib/pricing-tiers.ts`:
  - Line 98: `llmModel: "gpt-4o"` → `llmModel: "gpt-5.4-mini"` (OpenAI+Hume tier)
  - Line 142: Update Premium description to mention latest snapshot
  - Line 155: `llmModel: "gpt-realtime-2025-08-28"` → `llmModel: "gpt-realtime"` (use the alias that always points to latest)
  - Line 183: `llmModel: "gpt-4o-mini-realtime"` → `llmModel: "gpt-realtime-mini"` (use correct current model name)
  - Update feature descriptions as appropriate

**Verification:** `cd frontend && npm run lint && npm run build`

---

## Task 6: Update Grok Voice Constants with Latest Info

**Goal:** Update Grok voice descriptions and add any missing voices per latest xAI docs. Per research, the Grok Voice Agent API supports 5 voices. Our list currently has: Ara, Rex, Sal, Eve, Leo. The xAI docs confirm these 5 (Ara, Eve, Leo are mentioned explicitly, plus 2 others). The current list looks correct but descriptions could be more accurate per the official docs.

**Files to change:**
- `backend/app/services/ai/grok/constants.py`:
  - Update `GROK_VOICES` descriptions to match latest xAI docs more accurately
  - Update voice descriptions: Eve is "Professional, ideal for business use cases", Ara is "Default voice, balanced for general use", Leo is "Great for engaging, dynamic interactions"
  
- `frontend/src/lib/voice-constants.ts`:
  - Update `GROK_VOICES` array descriptions to match backend changes

**Verification:** `cd backend && uv run ruff check app && uv run mypy app` and `cd frontend && npm run lint && npm run build`

---

## Task 7: Update OpenAI TTS and Transcription Model References

**Goal:** Update the TTS model used for the embed chat endpoint and add latest transcription model reference.

**Files to change:**
- `backend/app/api/v1/embed.py`:
  - The chat endpoint at line 336 already uses `gpt-4o-mini` — this was handled in Task 1

- Add comment references in relevant files about the latest available audio models:
  - `gpt-4o-mini-tts-2025-12-15` (latest TTS with lower word error rates)
  - `gpt-4o-mini-transcribe-2025-12-15` (latest transcription with ~90% fewer hallucinations)

These are informational updates — the Realtime API uses built-in TTS/STT, but for any standalone TTS/transcription calls these are the latest snapshots.

**Verification:** `cd backend && uv run ruff check app && uv run mypy app`

---

## Execution Strategy

These tasks are independent and can run in parallel as subagents:

| Subagent | Tasks | Scope |
|----------|-------|-------|
| **Agent A** | Task 1 + Task 2 | Backend: OpenAI text models + embed API realtime model fix |
| **Agent B** | Task 4 + Task 7 | Backend: ElevenLabs model update + TTS/transcription refs |
| **Agent C** | Task 3 + Task 5 + Task 6 | Frontend: Voice constants + pricing tiers + Grok voices. Also update `backend/app/services/ai/grok/constants.py` for Grok voice descriptions |

### Risks
- **Model name accuracy**: The model names `gpt-5.4-nano` and `gpt-5.4-mini` need to match what OpenAI's API actually accepts. Based on research, these are the correct API model IDs.
- **Breaking changes**: The switch from `gpt-4o-mini` → `gpt-5.4-nano` should be backward compatible as these are drop-in replacements in the OpenAI API. Same response format.
- **ElevenLabs v3**: The `eleven_v3_conversational` model is added as an option but NOT made the default — `eleven_flash_v2_5` remains default for telephony due to lower latency.

### Verification
After all subagents complete:
```bash
cd backend && uv run ruff check app && uv run mypy app
cd frontend && npm run lint && npm run build
```
