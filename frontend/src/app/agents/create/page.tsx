import type { Metadata } from "next";

import { CreateAgentForm } from "@/components/agents/create-agent-form";
import { AppSidebar } from "@/components/layout/app-sidebar";

export const metadata: Metadata = {
  title: "Create Agent",
  description:
    "Create an AI voice agent: define its job, pick a starting point, choose a voice, write the prompt, and review before creating.",
};

export default function CreateAgentPage() {
  return (
    <AppSidebar>
      <CreateAgentForm />
    </AppSidebar>
  );
}
