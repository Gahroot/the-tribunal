import type { ContactStatus, CampaignStatus, MessageTestStatus, OpportunityStatus } from "@/types";

/**
 * Single source of truth for status presentation.
 *
 * Badges are neutral surfaces (see `StatusBadge`): the status word is the
 * accessible cue and semantic color appears only in the dot marker, using
 * theme tokens from globals.css (`--success`, `--warning`, `--info`,
 * `--destructive`, `--primary`, `--muted-foreground`). Raw palette classes
 * (green-500/red-500/...) are banned in app surfaces.
 *
 * Stage/status mapping keeps the original hue families: blue -> info,
 * amber/yellow -> warning, green -> success, red -> destructive, purple
 * -> primary (the money/action accent), gray -> neutral marker.
 */
export const contactStatusDotColors: Record<ContactStatus, string> = {
  new: "bg-info",
  contacted: "bg-warning",
  qualified: "bg-success",
  converted: "bg-primary",
  lost: "bg-destructive",
};

export const contactStatusLabels: Record<ContactStatus, string> = {
  new: "New",
  contacted: "Contacted",
  qualified: "Qualified",
  converted: "Converted",
  lost: "Lost",
};

export const campaignStatusDotColors: Record<CampaignStatus, string> = {
  draft: "bg-muted-foreground",
  scheduled: "bg-info",
  running: "bg-success",
  paused: "bg-warning",
  completed: "bg-muted-foreground",
  cancelled: "bg-destructive",
};

export const messageTestStatusDotColors: Record<MessageTestStatus, string> = {
  draft: "bg-muted-foreground",
  running: "bg-success",
  paused: "bg-warning",
  completed: "bg-muted-foreground",
};

export const appointmentStatusDotColors: Record<string, string> = {
  scheduled: "bg-info",
  completed: "bg-success",
  cancelled: "bg-destructive",
  no_show: "bg-muted-foreground",
};

export const opportunityStatusDotColors: Record<OpportunityStatus, string> = {
  open: "bg-info",
  won: "bg-success",
  lost: "bg-destructive",
  abandoned: "bg-muted-foreground",
};

export const callStatusDotColors: Record<string, string> = {
  completed: "bg-success",
  in_progress: "bg-info",
  initiated: "bg-info",
  ringing: "bg-warning",
  no_answer: "bg-muted-foreground",
  busy: "bg-warning",
  failed: "bg-destructive",
};
