// Core CRM Types

export type ContactStatus = "new" | "contacted" | "qualified" | "converted" | "lost";
export type PipelineStageType = "active" | "won" | "lost";
export type OpportunityStatus = "open" | "won" | "lost" | "abandoned";

export interface Contact {
  id: number;
  user_id: number;
  workspace_id?: string;
  first_name: string;
  last_name?: string;
  email?: string;
  phone_number?: string;
  company_name?: string;
  status: ContactStatus;
  tags?: string[] | string;
  notes?: string;
  created_at: string;
  updated_at: string;
  // Conversation metadata (from list endpoint)
  unread_count?: number;
  last_message_at?: string;
  last_message_direction?: MessageDirection;
  // AI Enrichment fields
  website_url?: string;
  linkedin_url?: string;
  business_intel?: BusinessIntel;
  enrichment_status?: EnrichmentStatus;
  enriched_at?: string;
}

export type EnrichmentStatus = "pending" | "enriched" | "failed" | "skipped";

export interface SocialLinks {
  linkedin?: string | null;
  facebook?: string | null;
  twitter?: string | null;
  instagram?: string | null;
  youtube?: string | null;
  tiktok?: string | null;
}

export interface WebsiteMeta {
  title?: string | null;
  description?: string | null;
}

export interface WebsiteSummary {
  business_description?: string | null;
  services?: string[];
  target_market?: string | null;
  unique_selling_points?: string[];
  industry?: string | null;
}

export interface GooglePlacesData {
  place_id: string;
  rating?: number | null;
  review_count?: number;
  types?: string[];
  business_status?: string;
}

export interface BusinessIntel {
  social_links?: SocialLinks;
  google_places?: GooglePlacesData;
  website_meta?: WebsiteMeta;
  website_summary?: WebsiteSummary;
  enrichment_error?: string;
  enrichment_failed_at?: string;
}

export type MessageDirection = "inbound" | "outbound";
export type MessageStatus = "queued" | "sending" | "sent" | "delivered" | "failed" | "received";
export type MessageChannel = "sms" | "email" | "voice" | "voicemail" | "note";

export interface Message {
  id: string;
  conversation_id?: string;
  contact_id: number;
  direction: MessageDirection;
  channel: MessageChannel;
  body: string;
  status: MessageStatus;
  from_number?: string;
  to_number?: string;
  is_ai: boolean;
  agent_id?: string;
  // For voice messages
  duration_seconds?: number;
  recording_url?: string;
  transcript?: string;
  // Timestamps
  created_at: string;
  sent_at?: string;
  delivered_at?: string;
}

export interface Conversation {
  id: string;
  user_id: string;
  workspace_id?: string;
  contact_id: number;
  contact?: Contact;
  status: "active" | "archived" | "blocked";
  unread_count: number;
  last_message_preview?: string;
  last_message_at?: string;
  last_message_direction?: MessageDirection;
  ai_enabled: boolean;
  ai_paused: boolean;
  assigned_agent_id?: string;
  // Follow-up settings
  followup_enabled?: boolean;
  followup_delay_hours?: number;
  followup_max_count?: number;
  followup_count_sent?: number;
  next_followup_at?: string;
  last_followup_at?: string;
  created_at: string;
  updated_at: string;
}

// Follow-up Types
export interface FollowupSettings {
  enabled: boolean;
  delay_hours: number;
  max_count: number;
  count_sent: number;
  next_followup_at?: string;
  last_followup_at?: string;
}

export interface FollowupGenerateResponse {
  message: string;
  conversation_id: string;
}

export interface FollowupSendResponse {
  success: boolean;
  message_id?: string;
  message_body: string;
}

export interface CallRecord {
  id: string;
  user_id: string;
  contact_id?: number;
  agent_id?: string;
  direction: "inbound" | "outbound";
  status: "initiated" | "ringing" | "in_progress" | "completed" | "failed" | "busy" | "no_answer";
  from_number: string;
  to_number: string;
  duration_seconds?: number;
  recording_url?: string;
  transcript?: string;
  emotion_data?: Record<string, unknown>;
  started_at: string;
  answered_at?: string;
  ended_at?: string;
  created_at: string;
}

export interface Appointment {
  id: number;
  contact_id: number;
  contact?: Contact;
  workspace_id?: string;
  agent_id?: string;
  scheduled_at: string;
  duration_minutes: number;
  status: "scheduled" | "completed" | "cancelled" | "no_show";
  service_type?: string;
  notes?: string;
  calcom_booking_uid?: string;
  calcom_booking_id?: number;
  calcom_event_type_id?: number;
  sync_status?: string;
  last_synced_at?: string;
  sync_error?: string;
  created_at: string;
  updated_at: string;
}

// Unified timeline item for the conversation feed
export type TimelineItemType = "sms" | "call" | "email" | "voicemail" | "appointment" | "note";

export interface TimelineItem {
  id: string;
  type: TimelineItemType;
  timestamp: string;
  direction?: MessageDirection;
  is_ai: boolean;
  // Content varies by type
  content: string;
  // Optional metadata
  duration_seconds?: number;
  recording_url?: string;
  transcript?: string;
  status?: string;
  // Reference to original record
  original_id: string;
  original_type: "sms_message" | "call_record" | "appointment" | "note";
}

// Pipeline & Opportunity types
export interface PipelineStage {
  id: string;
  pipeline_id: string;
  name: string;
  description?: string;
  order: number;
  probability: number; // 0-100
  stage_type: PipelineStageType;
  created_at: string;
  updated_at: string;
}

export interface Pipeline {
  id: string;
  workspace_id: string;
  name: string;
  description?: string;
  is_active: boolean;
  stages: PipelineStage[];
  created_at: string;
  updated_at: string;
}

export interface OpportunityLineItem {
  id: string;
  opportunity_id: string;
  name: string;
  description?: string;
  quantity: number;
  unit_price: number;
  discount: number;
  total: number;
  created_at: string;
  updated_at: string;
}

export interface OpportunityActivity {
  id: string;
  opportunity_id: string;
  activity_type: string;
  old_value?: string;
  new_value?: string;
  description?: string;
  created_at: string;
}

export interface Opportunity {
  id: string;
  workspace_id: string;
  pipeline_id: string;
  stage_id?: string;
  primary_contact_id?: number;
  assigned_user_id?: string;
  name: string;
  description?: string;
  amount?: number;
  currency: string;
  probability: number; // 0-100
  status: OpportunityStatus;
  lost_reason?: string;
  expected_close_date?: string;
  closed_date?: string;
  closed_by_id?: number;
  stage_changed_at?: string;
  source?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  line_items?: OpportunityLineItem[];
  activities?: OpportunityActivity[];
}

// Agent types
export interface Agent {
  id: string;
  user_id?: number;
  workspace_id?: string;
  name: string;
  description?: string | null;
  pricing_tier?: "budget" | "balanced" | "premium-mini" | "premium";
  system_prompt?: string;
  voice?: string;
  is_active: boolean;
  channel_mode: "voice" | "text" | "both" | string;
  created_at: string;
  updated_at: string;
}

// Workspace
export interface Workspace {
  id: string;
  user_id: number;
  name: string;
  description?: string;
  is_default: boolean;
  settings?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

// Automation types
export type AutomationTriggerType = "schedule" | "event" | "condition";
export type AutomationActionType = "send_sms" | "send_email" | "make_call" | "update_status" | "add_tag" | "assign_agent";

export interface AutomationAction {
  type: AutomationActionType;
  config: Record<string, unknown>;
}

export interface Automation {
  id: string;
  name: string;
  description?: string;
  trigger_type: AutomationTriggerType;
  trigger_config?: Record<string, unknown>;
  actions: AutomationAction[];
  is_active: boolean;
  last_triggered_at?: string;
  created_at: string;
  updated_at: string;
}

// Contact-Agent assignment
export interface ContactAgent {
  contact_id: number;
  agent_id: string;
  is_active: boolean;
  assigned_at: string;
}

// Quick Action type
export type QuickActionType =
  | "send_invoice"
  | "create_deal"
  | "schedule_appointment"
  | "add_to_campaign"
  | "send_followup"
  | "mark_vip"
  | "export_contact"
  | "archive_contact";

// Campaign Types
export type CampaignStatus = "draft" | "scheduled" | "running" | "paused" | "completed" | "cancelled";
export type CampaignType = "sms" | "email" | "voice" | "voice_sms_fallback" | "multi_channel";

export interface Campaign {
  id: string;
  workspace_id?: string;
  campaign_type: CampaignType;
  name: string;
  description?: string;
  status: CampaignStatus;
  from_phone_number: string;
  initial_message?: string;
  agent_id?: string;
  // Scheduling
  scheduled_start?: string;
  scheduled_end?: string;
  sending_hours_start?: string;
  sending_hours_end?: string;
  sending_days?: number[];
  timezone: string;
  // Rate limiting
  messages_per_minute: number;
  follow_up_enabled: boolean;
  follow_up_delay_hours: number;
  follow_up_message?: string;
  max_follow_ups: number;
  ai_enabled: boolean;
  qualification_criteria?: string;
  // Stats
  total_contacts: number;
  messages_sent: number;
  messages_delivered?: number;
  messages_failed?: number;
  replies_received: number;
  contacts_qualified: number;
  // Backwards compatibility - old field names
  type?: CampaignType;
  sent_count?: number;
  delivered_count?: number;
  responded_count?: number;
  failed_count?: number;
  sms_template?: string;
  email_subject?: string;
  email_template?: string;
  voice_script?: string;
  messages_per_hour?: number;
  max_retries?: number;
  retry_delay_minutes?: number;
  // Timestamps
  started_at?: string;
  completed_at?: string;
  created_at: string;
  updated_at: string;
}

export type CampaignContactStatus =
  | "pending"
  | "queued"
  | "sending"
  | "sent"
  | "delivered"
  | "failed"
  | "responded"
  | "opted_out"
  | "skipped";

export interface CampaignContact {
  id: string;
  campaign_id: string;
  contact_id: number;
  contact?: Contact;
  status: CampaignContactStatus;
  // Channel-specific delivery
  sms_status?: MessageStatus;
  email_status?: MessageStatus;
  call_status?: CallRecord["status"];
  // Tracking
  message_id?: string;
  call_id?: string;
  sent_at?: string;
  delivered_at?: string;
  responded_at?: string;
  failed_at?: string;
  failure_reason?: string;
  retry_count: number;
  next_retry_at?: string;
  // Personalization data
  personalization_data?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

// Campaign Worker Job Types
export type CampaignJobType = "send_message" | "make_call" | "retry_failed" | "process_batch";

export interface CampaignJob {
  id: string;
  campaign_id: string;
  campaign_contact_id: string;
  job_type: CampaignJobType;
  status: "pending" | "processing" | "completed" | "failed";
  attempts: number;
  max_attempts: number;
  scheduled_at: string;
  started_at?: string;
  completed_at?: string;
  error_message?: string;
  created_at: string;
}

// OpenAI Realtime Voice Types
export type RealtimeSessionStatus = "connecting" | "connected" | "active" | "disconnected" | "error";

export interface RealtimeSession {
  id: string;
  call_id: string;
  contact_id: number;
  agent_id: string;
  status: RealtimeSessionStatus;
  model: string;
  voice: string;
  // Audio settings
  input_audio_format: "pcm16" | "g711_ulaw" | "g711_alaw";
  output_audio_format: "pcm16" | "g711_ulaw" | "g711_alaw";
  // Turn detection
  turn_detection_type: "server_vad" | "none";
  turn_detection_threshold?: number;
  turn_detection_silence_ms?: number;
  // Conversation state
  conversation_items: RealtimeConversationItem[];
  // Timestamps
  started_at: string;
  ended_at?: string;
}

export interface RealtimeConversationItem {
  id: string;
  type: "message" | "function_call" | "function_call_output";
  role: "user" | "assistant" | "system";
  content: RealtimeContentPart[];
  status: "in_progress" | "completed" | "cancelled";
  created_at: string;
}

export interface RealtimeContentPart {
  type: "input_text" | "input_audio" | "text" | "audio";
  text?: string;
  audio?: string; // Base64 encoded audio
  transcript?: string;
}

export interface RealtimeEvent {
  type: string;
  event_id: string;
  // Session events
  session?: Partial<RealtimeSession>;
  // Conversation events
  item?: RealtimeConversationItem;
  // Audio events
  audio?: string;
  // Error events
  error?: {
    type: string;
    code: string;
    message: string;
  };
}

// Cal.com Integration Types
export interface CalcomConfig {
  id: string;
  user_id: number;
  workspace_id?: string;
  api_key: string;
  event_type_id: number;
  event_type_slug: string;
  calendar_id?: string;
  default_duration_minutes: number;
  buffer_before_minutes?: number;
  buffer_after_minutes?: number;
  booking_questions?: CalcomBookingQuestion[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CalcomBookingQuestion {
  name: string;
  type: "text" | "textarea" | "select" | "multiselect" | "phone" | "email";
  label: string;
  required: boolean;
  options?: string[];
}

export interface CalcomBooking {
  id: number;
  uid: string;
  user_id: number;
  contact_id: number;
  event_type_id: number;
  title: string;
  description?: string;
  start_time: string;
  end_time: string;
  timezone: string;
  status: "accepted" | "pending" | "cancelled" | "rejected";
  location?: string;
  meeting_url?: string;
  attendees: CalcomAttendee[];
  metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface CalcomAttendee {
  email: string;
  name: string;
  phone?: string;
  timezone: string;
}

export interface CalcomAvailability {
  date: string;
  slots: CalcomTimeSlot[];
}

export interface CalcomTimeSlot {
  start: string;
  end: string;
  available: boolean;
}

// Offer Types
export type DiscountType = "percentage" | "fixed" | "free_service";
export type GuaranteeType = "money_back" | "satisfaction" | "results";
export type UrgencyType = "limited_time" | "limited_quantity" | "expiring";

export interface ValueStackItem {
  name: string;
  description?: string;
  value: number;
  included: boolean;
}

export interface Offer {
  id: string;
  workspace_id: string;
  name: string;
  description?: string;
  discount_type: DiscountType;
  discount_value: number;
  terms?: string;
  valid_from?: string;
  valid_until?: string;
  is_active: boolean;
  // Hormozi-style fields
  headline?: string;
  subheadline?: string;
  regular_price?: number;
  offer_price?: number;
  savings_amount?: number;
  guarantee_type?: GuaranteeType;
  guarantee_days?: number;
  guarantee_text?: string;
  urgency_type?: UrgencyType;
  urgency_text?: string;
  scarcity_count?: number;
  value_stack_items?: ValueStackItem[];
  cta_text?: string;
  cta_subtext?: string;
  // Public landing page fields
  is_public?: boolean;
  public_slug?: string;
  require_email?: boolean;
  require_phone?: boolean;
  require_name?: boolean;
  page_views?: number;
  opt_ins?: number;
  // Computed fields
  lead_magnets?: LeadMagnet[];
  total_value?: number;
  created_at: string;
  updated_at: string;
}

// Lead Magnet Types
export type LeadMagnetType =
  | "pdf"
  | "video"
  | "checklist"
  | "template"
  | "webinar"
  | "free_trial"
  | "consultation"
  | "ebook"
  | "mini_course"
  | "quiz"
  | "calculator"
  | "rich_text"
  | "video_course";

export type DeliveryMethod = "email" | "download" | "redirect" | "sms";

export interface LeadMagnet {
  id: string;
  workspace_id: string;
  name: string;
  description?: string;
  magnet_type: LeadMagnetType;
  delivery_method: DeliveryMethod;
  content_url: string;
  thumbnail_url?: string;
  estimated_value?: number;
  content_data?: QuizContent | CalculatorContent | RichTextContent;
  is_active: boolean;
  download_count: number;
  created_at: string;
  updated_at: string;
}

// Quiz Types
export interface QuizOption {
  id: string;
  text: string;
  score: number;
}

export interface QuizQuestion {
  id: string;
  text: string;
  type: "single_choice" | "multiple_choice" | "scale";
  options: QuizOption[];
  weight?: number;
}

export interface QuizResult {
  id: string;
  min_score: number;
  max_score: number;
  title: string;
  description: string;
  cta_text?: string;
}

export interface QuizContent {
  title: string;
  description?: string;
  questions: QuizQuestion[];
  results: QuizResult[];
}

// Calculator Types
export interface CalculatorSelectOption {
  value: string;
  label: string;
  multiplier?: number;
}

export interface CalculatorInput {
  id: string;
  label: string;
  type: "number" | "currency" | "percentage" | "select";
  placeholder?: string;
  default_value?: number;
  prefix?: string;
  suffix?: string;
  help_text?: string;
  required: boolean;
  options?: CalculatorSelectOption[];
}

export interface CalculatorCalculation {
  id: string;
  label: string;
  formula: string;
  format: "currency" | "percentage" | "number";
}

export interface CalculatorOutput {
  id: string;
  label: string;
  formula: string;
  format: "currency" | "percentage" | "number" | "text";
  highlight: boolean;
  description?: string;
}

export interface CalculatorCTA {
  text: string;
  description?: string;
}

export interface CalculatorContent {
  title: string;
  description?: string;
  inputs: CalculatorInput[];
  calculations: CalculatorCalculation[];
  outputs: CalculatorOutput[];
  cta?: CalculatorCTA;
}

// Rich Text Content
export interface RichTextContent {
  title: string;
  description?: string;
  content: unknown; // TipTap JSON format
}

export interface OfferLeadMagnet {
  id: string;
  offer_id: string;
  lead_magnet_id: string;
  sort_order: number;
  is_bonus: boolean;
  created_at: string;
  lead_magnet: LeadMagnet;
}

// Phone Number Types
export interface PhoneNumber {
  id: string;
  workspace_id: string;
  phone_number: string;
  friendly_name?: string;
  sms_enabled: boolean;
  voice_enabled: boolean;
  mms_enabled: boolean;
  assigned_agent_id?: string;
  is_active: boolean;
}

// Voice Campaign Types
export type VoiceCampaignContactStatus =
  | "pending"
  | "calling"
  | "call_answered"
  | "call_failed"
  | "sms_fallback_sent"
  | "responded"
  | "qualified"
  | "opted_out";

export interface VoiceCampaign {
  id: string;
  workspace_id: string;
  campaign_type: "voice_sms_fallback";
  name: string;
  description?: string;
  status: CampaignStatus;
  from_phone_number: string;

  // Voice settings
  voice_agent_id?: string;
  voice_connection_id?: string;
  enable_machine_detection: boolean;
  max_call_duration_seconds: number;
  calls_per_minute: number;

  // SMS fallback settings
  sms_fallback_enabled: boolean;
  sms_fallback_template?: string;
  sms_fallback_use_ai: boolean;
  sms_fallback_agent_id?: string;

  // AI settings (for responses to SMS replies)
  ai_enabled: boolean;
  agent_id?: string;
  qualification_criteria?: string;

  // Scheduling
  scheduled_start?: string;
  scheduled_end?: string;
  sending_hours_start?: string;
  sending_hours_end?: string;
  sending_days?: number[];
  timezone: string;

  // Statistics
  total_contacts: number;
  calls_attempted: number;
  calls_answered: number;
  calls_no_answer: number;
  calls_busy: number;
  calls_voicemail: number;
  sms_fallbacks_sent: number;
  messages_sent: number;
  replies_received: number;
  contacts_qualified: number;
  contacts_opted_out: number;
  appointments_booked: number;

  // Timestamps
  started_at?: string;
  completed_at?: string;
  created_at: string;
  updated_at: string;
}

export interface VoiceCampaignContact {
  id: string;
  campaign_id: string;
  contact_id: number;
  contact?: Contact;
  conversation_id?: string;
  status: VoiceCampaignContactStatus;

  // Call tracking
  call_attempts: number;
  last_call_at?: string;
  last_call_status?: string;
  call_duration_seconds?: number;

  // SMS fallback tracking
  sms_fallback_sent: boolean;
  sms_fallback_sent_at?: string;

  // Standard fields
  messages_sent: number;
  is_qualified: boolean;
  opted_out: boolean;
  created_at: string;
}

export interface VoiceCampaignAnalytics {
  total_contacts: number;
  calls_attempted: number;
  calls_answered: number;
  calls_no_answer: number;
  calls_busy: number;
  calls_voicemail: number;
  sms_fallbacks_sent: number;
  messages_sent: number;
  replies_received: number;
  contacts_qualified: number;
  contacts_opted_out: number;
  appointments_booked: number;
  // Rates
  answer_rate: number;
  fallback_rate: number;
  qualification_rate: number;
}

// SMS Campaign Types (extended)
export interface SMSCampaign {
  id: string;
  workspace_id: string;
  agent_id?: string;
  offer_id?: string;
  name: string;
  description?: string;
  status: CampaignStatus;
  from_phone_number: string;
  initial_message: string;
  ai_enabled: boolean;
  qualification_criteria?: string;
  // Scheduling
  scheduled_start?: string;
  scheduled_end?: string;
  sending_hours_start?: string;
  sending_hours_end?: string;
  sending_days?: number[];
  timezone: string;
  // Rate limiting
  messages_per_minute: number;
  max_messages_per_contact: number;
  // Follow-ups
  follow_up_enabled: boolean;
  follow_up_delay_hours: number;
  follow_up_message?: string;
  max_follow_ups: number;
  // Stats
  total_contacts: number;
  messages_sent: number;
  messages_delivered: number;
  messages_failed: number;
  replies_received: number;
  contacts_qualified: number;
  contacts_opted_out: number;
  appointments_booked: number;
  // Timestamps
  started_at?: string;
  completed_at?: string;
  created_at: string;
  updated_at: string;
}

// Message Test Types (A/B Testing)
export type MessageTestStatus = "draft" | "running" | "paused" | "completed";
export type TestContactStatus =
  | "pending"
  | "sent"
  | "delivered"
  | "replied"
  | "qualified"
  | "opted_out"
  | "failed";

export interface TestVariant {
  id: string;
  message_test_id: string;
  name: string;
  message_template: string;
  is_control: boolean;
  sort_order: number;
  contacts_assigned: number;
  messages_sent: number;
  replies_received: number;
  contacts_qualified: number;
  response_rate: number;
  qualification_rate: number;
  created_at: string;
  updated_at: string;
}

export interface TestContact {
  id: string;
  message_test_id: string;
  contact_id: number;
  variant_id?: string;
  conversation_id?: string;
  status: TestContactStatus;
  is_qualified: boolean;
  opted_out: boolean;
  first_sent_at?: string;
  last_reply_at?: string;
  variant_assigned_at?: string;
  created_at: string;
}

export interface MessageTest {
  id: string;
  workspace_id: string;
  agent_id?: string;
  name: string;
  description?: string;
  status: MessageTestStatus;
  from_phone_number: string;
  use_number_pool: boolean;
  ai_enabled: boolean;
  qualification_criteria?: string;
  sending_hours_start?: string;
  sending_hours_end?: string;
  sending_days?: number[];
  timezone: string;
  messages_per_minute: number;
  total_contacts: number;
  total_variants: number;
  messages_sent: number;
  replies_received: number;
  contacts_qualified: number;
  winning_variant_id?: string;
  converted_to_campaign_id?: string;
  started_at?: string;
  completed_at?: string;
  created_at: string;
  updated_at: string;
  variants?: TestVariant[];
}

export interface VariantAnalytics {
  variant_id: string;
  variant_name: string;
  is_control: boolean;
  contacts_assigned: number;
  messages_sent: number;
  replies_received: number;
  contacts_qualified: number;
  response_rate: number;
  qualification_rate: number;
}

export interface MessageTestAnalytics {
  test_id: string;
  test_name: string;
  status: MessageTestStatus;
  total_contacts: number;
  total_variants: number;
  messages_sent: number;
  replies_received: number;
  contacts_qualified: number;
  overall_response_rate: number;
  overall_qualification_rate: number;
  variants: VariantAnalytics[];
  winning_variant_id?: string;
  statistical_significance: boolean;
}
