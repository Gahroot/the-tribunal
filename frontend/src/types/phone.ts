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
