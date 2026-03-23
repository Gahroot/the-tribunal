import { Zap, Crown, Sparkles, Shield, AlertTriangle, ShieldAlert } from "lucide-react";
import { AVAILABLE_INTEGRATIONS, type ToolRiskLevel } from "@/lib/integrations";

export const INTEGRATIONS_WITH_TOOLS = AVAILABLE_INTEGRATIONS.filter(
  (i) => i.tools && i.tools.length > 0
);

export function getRiskLevelBadge(level: ToolRiskLevel) {
  switch (level) {
    case "safe":
      return { variant: "outline" as const, icon: Shield, color: "text-success" };
    case "moderate":
      return { variant: "outline" as const, icon: AlertTriangle, color: "text-warning" };
    case "high":
      return { variant: "outline" as const, icon: ShieldAlert, color: "text-destructive" };
  }
}

export function getTierIcon(tierId: string) {
  switch (tierId) {
    case "budget":
      return Zap;
    case "premium":
      return Crown;
    default:
      return Sparkles;
  }
}
