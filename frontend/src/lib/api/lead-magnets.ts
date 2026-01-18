import api from "@/lib/api";
import type {
  LeadMagnet,
  LeadMagnetType,
  DeliveryMethod,
  QuizContent,
  CalculatorContent,
  RichTextContent,
} from "@/types";

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

// Lead Magnets API
export const leadMagnetsApi = {
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

  list: async (
    workspaceId: string,
    params: LeadMagnetsListParams = {}
  ): Promise<LeadMagnetsListResponse> => {
    const response = await api.get<LeadMagnetsListResponse>(
      `/api/v1/workspaces/${workspaceId}/lead-magnets`,
      { params }
    );
    return response.data;
  },

  get: async (workspaceId: string, leadMagnetId: string): Promise<LeadMagnet> => {
    const response = await api.get<LeadMagnet>(
      `/api/v1/workspaces/${workspaceId}/lead-magnets/${leadMagnetId}`
    );
    return response.data;
  },

  create: async (
    workspaceId: string,
    data: CreateLeadMagnetRequest
  ): Promise<LeadMagnet> => {
    const response = await api.post<LeadMagnet>(
      `/api/v1/workspaces/${workspaceId}/lead-magnets`,
      data
    );
    return response.data;
  },

  update: async (
    workspaceId: string,
    leadMagnetId: string,
    data: UpdateLeadMagnetRequest
  ): Promise<LeadMagnet> => {
    const response = await api.put<LeadMagnet>(
      `/api/v1/workspaces/${workspaceId}/lead-magnets/${leadMagnetId}`,
      data
    );
    return response.data;
  },

  delete: async (workspaceId: string, leadMagnetId: string): Promise<void> => {
    await api.delete(
      `/api/v1/workspaces/${workspaceId}/lead-magnets/${leadMagnetId}`
    );
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
