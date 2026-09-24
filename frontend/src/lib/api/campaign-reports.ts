import { apiGet, apiPost } from "@/lib/api";

// Types

export interface CampaignReportFinding {
  title: string;
  description: string;
  metric?: string;
  sentiment?: "positive" | "negative" | "neutral";
}

export interface CampaignReportEvidence {
  title: string;
  description: string;
  evidence?: string;
}

export interface CampaignReportRecommendation {
  title: string;
  description: string;
  priority: "high" | "medium" | "low";
  action_type: string;
}

export interface CampaignReportSegment {
  segment_name: string;
  size: number;
  conversion_rate: number;
  insights: string;
}

export interface CampaignReportTimingAnalysis {
  best_hours?: number[];
  worst_hours?: number[];
  best_days?: string[];
  worst_days?: string[];
  recommendation?: string;
}

export interface CampaignReportResponse {
  id: string;
  campaign_id: string;
  workspace_id: string;
  campaign_name: string | null;
  campaign_type: string | null;

  status: string;
  error_message: string | null;

  metrics_snapshot: Record<string, number> | null;
  executive_summary: string | null;
  key_findings: CampaignReportFinding[] | null;
  what_worked: CampaignReportEvidence[] | null;
  what_didnt_work: CampaignReportEvidence[] | null;
  recommendations: CampaignReportRecommendation[] | null;
  segment_analysis: CampaignReportSegment[] | null;
  timing_analysis: CampaignReportTimingAnalysis | null;
  prompt_performance: Array<{
    version_id: string;
    calls: number;
    successful: number;
    success_rate: number;
  }> | null;

  generated_suggestion_ids: string[] | null;
  generated_at: string | null;
  created_at: string;
}

export interface CampaignReportSummary {
  id: string;
  campaign_id: string;
  campaign_name: string | null;
  campaign_type: string | null;
  status: string;
  executive_summary: string | null;
  generated_at: string | null;
  created_at: string;
}

export interface CampaignReportListResponse {
  items: CampaignReportSummary[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface CampaignReportListParams {
  status?: string;
  page?: number;
  page_size?: number;
}

export interface AttemptFunnelMetrics {
  calls: number;
  connected: number;
  conversations: number;
  qualified: number;
  booked: number;
  shown: number;
  connect_rate: number;
  conversation_rate: number;
  qualified_rate: number;
  booked_rate: number;
  shown_rate: number;
  show_rate_of_booked: number | null;
  estimated_cost_usd: number;
  estimated_cost_per_call_usd: number;
  estimated_cost_per_booked_usd: number | null;
  estimated_cost_per_shown_usd: number | null;
}

export interface AttemptFunnel {
  starts_at: string;
  ends_at: string;
  hour_timezone: string;
  cost_basis: string;
  overall: AttemptFunnelMetrics;
  attempt: Array<AttemptFunnelMetrics & { value: number }>;
  hour_utc: Array<AttemptFunnelMetrics & { value: number }>;
  lead_source: Array<AttemptFunnelMetrics & { value: string }>;
  campaign: Array<AttemptFunnelMetrics & { value: string; campaign_name: string }>;
}

// API

export const campaignReportsApi = {
  attemptFunnel: (workspaceId: string, days = 30): Promise<AttemptFunnel> =>
    apiGet<AttemptFunnel>(`/api/v1/workspaces/${workspaceId}/campaign-reports/attempt-funnel`, {
      params: { days },
    }),
  list: async (
    workspaceId: string,
    params: CampaignReportListParams = {}
  ): Promise<CampaignReportListResponse> => {
    return apiGet<CampaignReportListResponse>(
      `/api/v1/workspaces/${workspaceId}/campaign-reports`,
      { params }
    );
  },

  get: async (workspaceId: string, reportId: string): Promise<CampaignReportResponse> => {
    return apiGet<CampaignReportResponse>(
      `/api/v1/workspaces/${workspaceId}/campaign-reports/${reportId}`
    );
  },

  getByCampaign: async (
    workspaceId: string,
    campaignId: string
  ): Promise<CampaignReportResponse> => {
    return apiGet<CampaignReportResponse>(
      `/api/v1/workspaces/${workspaceId}/campaign-reports/campaign/${campaignId}`
    );
  },

  generate: async (
    workspaceId: string,
    campaignId: string
  ): Promise<CampaignReportResponse> => {
    return apiPost<CampaignReportResponse>(
      `/api/v1/workspaces/${workspaceId}/campaign-reports/campaign/${campaignId}/generate`
    );
  },

  getCount: async (workspaceId: string): Promise<{ report_count: number }> => {
    return apiGet<{ report_count: number }>(
      `/api/v1/workspaces/${workspaceId}/campaign-reports/count`
    );
  },
};
