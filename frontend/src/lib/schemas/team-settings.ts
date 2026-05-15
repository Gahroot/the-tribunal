import * as z from "zod";

/**
 * Workspace identity form — name + description.
 * Used by the "Workspace Settings" card in TeamSettingsTab.
 *
 * Schemas use plain `string` (not `.optional()`) so input and output types
 * match — react-hook-form's `Resolver` needs the same shape on both sides.
 * Empty strings are filtered to `undefined` when building the API request.
 */
export const workspaceFormSchema = z.object({
  name: z
    .string()
    .max(120, { error: "Workspace name must be 120 characters or less" }),
  description: z
    .string()
    .max(500, { error: "Description must be 500 characters or less" }),
});

export type WorkspaceFormValues = z.infer<typeof workspaceFormSchema>;

export const emptyWorkspaceFormValues: WorkspaceFormValues = {
  name: "",
  description: "",
};

/**
 * Company information form — business details stored on workspace.settings.
 * Used by the "Company Information" card in TeamSettingsTab.
 */
export const companyFormSchema = z.object({
  business_name: z.string().max(200),
  phone: z.string().max(40),
  website: z.string().max(300),
  address: z.string().max(300),
  city: z.string().max(120),
  state: z.string().max(120),
  postal_code: z.string().max(40),
  country: z.string().max(120),
  timezone: z.string().min(1),
});

export type CompanyFormValues = z.infer<typeof companyFormSchema>;

export const emptyCompanyFormValues: CompanyFormValues = {
  business_name: "",
  phone: "",
  website: "",
  address: "",
  city: "",
  state: "",
  postal_code: "",
  country: "",
  timezone: "America/New_York",
};
