export interface VoiceOption {
  id: string;
  name: string;
  description: string;
  recommended?: boolean;
}

// OpenAI Realtime API voices (for Premium tier)
export const REALTIME_VOICES: VoiceOption[] = [
  { id: "marin", name: "Marin", description: "Professional & clear (Recommended)", recommended: true },
  { id: "cedar", name: "Cedar", description: "Natural & conversational (Recommended)", recommended: true },
  { id: "alloy", name: "Alloy", description: "Neutral and balanced" },
  { id: "ash", name: "Ash", description: "Clear and precise" },
  { id: "ballad", name: "Ballad", description: "Melodic and smooth" },
  { id: "coral", name: "Coral", description: "Warm and friendly" },
  { id: "echo", name: "Echo", description: "Warm and engaging" },
  { id: "fable", name: "Fable", description: "Expressive and dramatic" },
  { id: "nova", name: "Nova", description: "Friendly and upbeat" },
  { id: "onyx", name: "Onyx", description: "Deep and authoritative" },
  { id: "sage", name: "Sage", description: "Calm and thoughtful" },
  { id: "shimmer", name: "Shimmer", description: "Energetic and expressive" },
  { id: "verse", name: "Verse", description: "Versatile and expressive" },
];

// Hume Octave voices (for openai-hume tier)
export const HUME_VOICES: VoiceOption[] = [
  { id: "kora", name: "Kora", description: "Warm and professional (Recommended)", recommended: true },
  { id: "melanie", name: "Melanie", description: "Natural and expressive (Recommended)", recommended: true },
  { id: "aoede", name: "Aoede", description: "Clear and articulate" },
  { id: "orpheus", name: "Orpheus", description: "Rich and expressive" },
  { id: "charon", name: "Charon", description: "Deep and authoritative" },
  { id: "calliope", name: "Calliope", description: "Melodic and friendly" },
  { id: "atlas", name: "Atlas", description: "Strong and confident" },
  { id: "helios", name: "Helios", description: "Bright and energetic" },
  { id: "luna", name: "Luna", description: "Soft and calming" },
];

// Grok (xAI) voices - supports realism cues like [whisper], [sigh], [laugh]
export const GROK_VOICES: VoiceOption[] = [
  { id: "ara", name: "Ara", description: "Warm & friendly female (Recommended)", recommended: true },
  { id: "rex", name: "Rex", description: "Confident & clear male" },
  { id: "sal", name: "Sal", description: "Smooth & balanced neutral" },
  { id: "eve", name: "Eve", description: "Energetic & upbeat female" },
  { id: "leo", name: "Leo", description: "Authoritative & strong male" },
];

// ElevenLabs voices - premium TTS with 100+ expressive voices
export const ELEVENLABS_VOICES: VoiceOption[] = [
  { id: "ava", name: "Ava", description: "Natural female (Recommended)", recommended: true },
  { id: "lisa", name: "Lisa", description: "Friendly female" },
  { id: "sarah_eve", name: "Sarah Eve", description: "Expressive female" },
  { id: "rachel", name: "Rachel", description: "Calm female" },
  { id: "bella", name: "Bella", description: "Soft female" },
  { id: "antoni", name: "Antoni", description: "Young male" },
  { id: "josh", name: "Josh", description: "Deep male" },
  { id: "adam", name: "Adam", description: "Narrator male" },
  { id: "sam", name: "Sam", description: "Raspy male" },
  { id: "domi", name: "Domi", description: "Strong female" },
  { id: "elli", name: "Elli", description: "Young female" },
  { id: "callum", name: "Callum", description: "Transatlantic male" },
  { id: "charlie", name: "Charlie", description: "Casual male" },
  { id: "charlotte", name: "Charlotte", description: "Swedish female" },
  { id: "daniel", name: "Daniel", description: "British male" },
  { id: "emily", name: "Emily", description: "Calm female" },
  { id: "freya", name: "Freya", description: "American female" },
  { id: "giovanni", name: "Giovanni", description: "Italian male" },
  { id: "grace", name: "Grace", description: "Southern female" },
  { id: "lily", name: "Lily", description: "British female" },
  { id: "matilda", name: "Matilda", description: "Warm female" },
  { id: "river", name: "River", description: "Confident female" },
  { id: "serena", name: "Serena", description: "Pleasant female" },
  { id: "thomas", name: "Thomas", description: "Calm male" },
];

// Grok built-in tools - these are native capabilities that auto-execute
export const GROK_BUILTIN_TOOLS = [
  {
    id: "web_search",
    name: "Web Search",
    description:
      "Search the web for current events, prices, news, weather, and real-time information. Grok automatically decides when to search.",
  },
  {
    id: "x_search",
    name: "X (Twitter) Search",
    description:
      "Search X/Twitter for trending topics, public opinions, and recent posts. Great for understanding what people are saying.",
  },
];

// Best practices system prompt template
export const BEST_PRACTICES_PROMPT = `# Role & Identity
You are a helpful phone assistant for [COMPANY_NAME]. You help customers with questions, support requests, and general inquiries.

# Personality & Tone
- Warm, concise, and confident—never fawning or overly enthusiastic
- Keep responses to 2-3 sentences maximum
- Speak at a steady, unhurried pace
- Use occasional natural fillers like "let me check that" for conversational flow

# Language Rules
- ALWAYS respond in the same language the customer uses
- If audio is unclear, say: "Sorry, I didn't catch that. Could you repeat?"
- Never switch languages mid-conversation unless asked

# Turn-Taking
- Wait for the customer to finish speaking before responding
- Use brief acknowledgments: "Got it," "I understand," "Let me help with that"
- Vary your responses—never repeat the same phrase twice in a row

# Alphanumeric Handling
- When reading back phone numbers, spell digit by digit: "4-1-5-5-5-5-1-2-3-4"
- For confirmation codes, say each character separately
- Always confirm: "Just to verify, that's [X]. Is that correct?"

# Tool Usage
- For lookups: Call immediately, say "Let me check that for you"
- For changes: Confirm first: "I'll update that now. Is that correct?"

# Escalation
Transfer to a human when:
- Customer explicitly requests it
- Customer expresses frustration
- You cannot resolve their issue after 2 attempts
- Request is outside your capabilities

# Boundaries
- Stay focused on [COMPANY_NAME] services
- If unsure, say: "Let me transfer you to someone who can help with that"
- Be honest when you don't know something`;
