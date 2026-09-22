/**
 * Centralized user-facing toast/notification copy.
 *
 * Grouped by domain. Each leaf is either a string constant or a small
 * function returning a string when the message needs dynamic values.
 *
 * Patterns:
 *   - `success` — confirmation of a completed action
 *   - `error`   — fallback string for failure paths (pair with `getApiErrorMessage`)
 *   - `info`    — neutral notice (validation, prerequisites)
 *
 * Add new entries near related domains rather than creating new top-level
 * groups unless a clearly distinct domain is introduced.
 */

export const messages = {
  agents: {
    notFound: "Agent not found or has been deleted",
    updated: "Agent updated successfully",
    updateFailed: "Failed to update agent",
    deleted: "Agent deleted successfully",
    deleteFailed: "Failed to delete agent",
    promptImproveFailed: "Couldn't generate a prompt suggestion. Please try again.",
    promptImproveTookAction:
      "The assistant ran a CRM action instead of rewriting. Review Approvals, then try again.",
    promptSuggestionInserted: "Suggestion inserted — review and save your changes",
    promptReset: "Prompt reset to the last saved version",
  },

  campaigns: {
    smsCreated: "Campaign created successfully!",
    smsCreateFailed: "Failed to create campaign",
    smsSent: "Campaign sent — it is now live in your campaign list",
    startFailed: "Campaign created but it could not start sending",
    aiDraftInserted: "AI draft inserted — review and edit before sending",
    aiDraftFailed: "Failed to generate a draft. Try again.",
    voiceCreated: "Voice campaign created successfully!",
    voiceCreateFailed: "Failed to create campaign",
  },

  offers: {
    created: "Offer created successfully",
    createFailed: "Failed to create offer",
  },

  contacts: {
    created: "Contact created successfully!",
    createFailed: "Failed to create contact. Please try again.",
    updated: "Contact updated successfully!",
    updateFailed: "Failed to update contact. Please try again.",
    deleted: "Contact deleted successfully",
    deleteFailed: "Failed to delete contact. Please try again.",
    noPhoneNumber: "Contact has no phone number",
    aiEnabled: "AI engagement enabled!",
    aiDisabled: "AI engagement disabled!",
    aiToggleFailed: "Failed to toggle AI engagement. Please try again.",
  },

  phoneNumbers: {
    noneVoiceEnabled: "No voice-enabled phone numbers available",
  },

  findLeads: {
    found: (count: number) => `Found ${count} businesses`,
    searchFailed: "Failed to search. Please check your API key configuration.",
    queryRequired: "Please enter a search query",
    selectionRequired: "Please select at least one lead to import",
  },

  workspace: {
    notLoaded: "Workspace not loaded",
  },
} as const;
