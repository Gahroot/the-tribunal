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
