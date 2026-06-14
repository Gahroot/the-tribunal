import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { CampaignDetail } from "@/components/campaigns/campaign-detail";
import type { Campaign, VoiceCampaignAnalytics } from "@/types";

const {
  getCampaignMock,
  getSmsAnalyticsMock,
  getVoiceAnalyticsMock,
  useWorkspaceIdMock,
} = vi.hoisted(() => ({
  getCampaignMock: vi.fn(),
  getSmsAnalyticsMock: vi.fn(),
  getVoiceAnalyticsMock: vi.fn(),
  useWorkspaceIdMock: vi.fn(),
}));

vi.mock("@/hooks/useWorkspaceId", () => ({
  useWorkspaceId: () => useWorkspaceIdMock(),
}));

vi.mock("@/lib/api/campaigns", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/campaigns")>(
    "@/lib/api/campaigns",
  );
  return {
    ...actual,
    campaignsApi: {
      ...actual.campaignsApi,
      get: getCampaignMock,
      getAnalytics: getSmsAnalyticsMock,
      start: vi.fn(),
      pause: vi.fn(),
      resume: vi.fn(),
      cancel: vi.fn(),
    },
  };
});

vi.mock("@/lib/api/voice-campaigns", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api/voice-campaigns")>(
    "@/lib/api/voice-campaigns",
  );
  return {
    ...actual,
    voiceCampaignsApi: {
      ...actual.voiceCampaignsApi,
      getAnalytics: getVoiceAnalyticsMock,
    },
  };
});

function renderCampaignDetail() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <CampaignDetail campaignId="campaign_voice_1" />
    </QueryClientProvider>,
  );
}

function baseCampaign(overrides: Partial<Campaign> = {}): Campaign {
  return {
    id: "campaign_voice_1",
    workspace_id: "workspace_1",
    campaign_type: "voice_sms_fallback",
    name: "First Run Voice Campaign",
    status: "draft",
    from_phone_number: "+15551234567",
    timezone: "America/New_York",
    messages_per_minute: 10,
    follow_up_enabled: false,
    follow_up_delay_hours: 24,
    max_follow_ups: 0,
    ai_enabled: true,
    total_contacts: 50,
    messages_sent: 0,
    messages_delivered: 0,
    messages_failed: 0,
    replies_received: 0,
    contacts_qualified: 4,
    contacts_opted_out: 1,
    appointments_booked: 3,
    appointments_completed: 2,
    created_at: "2026-01-02T03:04:05Z",
    updated_at: "2026-01-02T03:04:05Z",
    ...overrides,
  };
}

const voiceAnalytics: VoiceCampaignAnalytics = {
  total_contacts: 50,
  calls_attempted: 25,
  calls_answered: 10,
  calls_no_answer: 8,
  calls_busy: 1,
  calls_voicemail: 6,
  sms_fallbacks_sent: 14,
  messages_sent: 14,
  replies_received: 2,
  contacts_qualified: 4,
  contacts_opted_out: 1,
  appointments_booked: 3,
  answer_rate: 40,
  fallback_rate: 93.3333333333,
  qualification_rate: 33.3333333333,
};

describe("CampaignDetail", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceIdMock.mockReturnValue("workspace_1");
  });

  it("renders voice call statistics from voice campaign analytics", async () => {
    getCampaignMock.mockResolvedValue(baseCampaign());
    getVoiceAnalyticsMock.mockResolvedValue(voiceAnalytics);

    renderCampaignDetail();

    expect(await screen.findByText("Call Statistics")).toBeInTheDocument();

    await waitFor(() => {
      expect(getVoiceAnalyticsMock).toHaveBeenCalledWith("workspace_1", "campaign_voice_1");
    });

    expect(getSmsAnalyticsMock).not.toHaveBeenCalled();
    expect(screen.getByText("Dialed")).toBeInTheDocument();
    expect(screen.getByText("Answered")).toBeInTheDocument();
    expect(screen.getByText("Answer Rate")).toBeInTheDocument();
    expect(screen.getByText("No Answer")).toBeInTheDocument();
    expect(screen.getByText("Voicemail")).toBeInTheDocument();
    expect(screen.getByText("SMS Fallbacks")).toBeInTheDocument();
    expect(screen.getByText("Booked")).toBeInTheDocument();
    expect(screen.getByText("40.0%")).toBeInTheDocument();
    expect(screen.getByText("25")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.queryByText("Delivered")).not.toBeInTheDocument();
  });
});
