import api from "@/lib/api";
import type {
  LeadMagnet,
  LeadMagnetType,
  DeliveryMethod,
  QuizContent,
  CalculatorContent,
  RichTextContent,
} from "@/types";
import { createApiClient, type FullApiClient } from "@/lib/api/create-api-client";

// Request/Response Types
export interface LeadMagnetsListParams {
  page?: number;
  page_size?: number;
  active_only?: boolean;
  magnet_type?: LeadMagnetType;
}

export interface LeadMagnetsListResponse {
  items: LeadMagnet[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface CreateLeadMagnetRequest {
  name: string;
  description?: string;
  magnet_type: LeadMagnetType;
  delivery_method: DeliveryMethod;
  content_url?: string;
  thumbnail_url?: string;
  estimated_value?: number;
  content_data?: QuizContent | CalculatorContent | RichTextContent | Record<string, unknown>;
  is_active?: boolean;
}

export interface UpdateLeadMagnetRequest {
  name?: string;
  description?: string;
  magnet_type?: LeadMagnetType;
  delivery_method?: DeliveryMethod;
  content_url?: string;
  thumbnail_url?: string;
  estimated_value?: number;
  content_data?: QuizContent | CalculatorContent | RichTextContent | Record<string, unknown>;
  is_active?: boolean;
}

// Quiz Generation Types
export interface GenerateQuizRequest {
  topic: string;
  target_audience: string;
  goal: string;
  num_questions?: number;
}

export interface GeneratedQuizContent extends QuizContent {
  success: boolean;
  error?: string;
}

// Calculator Generation Types
export interface GenerateCalculatorRequest {
  calculator_type: string;
  industry: string;
  target_audience: string;
  value_proposition: string;
}

export interface GeneratedCalculatorContent extends CalculatorContent {
  success: boolean;
  error?: string;
}

const baseApi = createApiClient<LeadMagnet, CreateLeadMagnetRequest, UpdateLeadMagnetRequest>({
  resourcePath: "lead-magnets",
}) as FullApiClient<LeadMagnet, CreateLeadMagnetRequest, UpdateLeadMagnetRequest>;

// Lead Magnets API
export const leadMagnetsApi = {
  ...baseApi,

  // AI Generation
  generateQuiz: async (
    workspaceId: string,
    data: GenerateQuizRequest
  ): Promise<GeneratedQuizContent> => {
    const response = await api.post<GeneratedQuizContent>(
      `/api/v1/workspaces/${workspaceId}/lead-magnets/generate-quiz`,
      data
    );
    return response.data;
  },

  generateCalculator: async (
    workspaceId: string,
    data: GenerateCalculatorRequest
  ): Promise<GeneratedCalculatorContent> => {
    const response = await api.post<GeneratedCalculatorContent>(
      `/api/v1/workspaces/${workspaceId}/lead-magnets/generate-calculator`,
      data
    );
    return response.data;
  },

  incrementDownload: async (
    workspaceId: string,
    leadMagnetId: string
  ): Promise<LeadMagnet> => {
    const response = await api.post<LeadMagnet>(
      `/api/v1/workspaces/${workspaceId}/lead-magnets/${leadMagnetId}/increment-download`
    );
    return response.data;
  },
};
