"use client";

import {
  CalendarCheck,
  FileText,
  LifeBuoy,
  Phone,
  RefreshCw,
  Users,
  type LucideIcon,
} from "lucide-react";
import type { UseFormReturn } from "react-hook-form";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

import type { AgentFormValues } from "./create-agent-form";

interface StartingPoint {
  id: string;
  name: string;
  blurb: string;
  icon: LucideIcon;
  systemPrompt: string;
  initialGreeting: string;
}

/**
 * Local starter personas — there is no backend endpoint for agent templates,
 * so the wizard ships its own prefills. Applying one replaces the draft
 * system prompt and greeting; everything stays editable in the prompt step.
 */
const STARTING_POINTS: StartingPoint[] = [
  {
    id: "scratch",
    name: "Start from scratch",
    blurb: "Blank prompt: write your own instructions from the ground up.",
    icon: FileText,
    systemPrompt: "",
    initialGreeting: "",
  },
  {
    id: "qualifier",
    name: "Lead Qualifier",
    blurb: "Qualify inbound leads on budget, timeline, and intent, then hand off warm.",
    icon: Users,
    systemPrompt: `You are a friendly lead qualifier for [Company Name].

Your job:
- Greet the caller, confirm who you are speaking with, and ask what brought them in
- Qualify with four questions: budget range, timeline, preferred area, and whether they are buying or selling
- Capture the best phone number and email before wrapping up
- Offer to book a call with an agent while you have them

Style:
- Keep replies to 2-3 sentences and ask one question at a time
- Sound warm and unhurried, never scripted
- If they are not ready to move forward, thank them and note the follow-up reason`,
    initialGreeting:
      "Hi, this is the assistant at [Company Name]. What brought you in today?",
  },
  {
    id: "setter",
    name: "Appointment Setter",
    blurb: "Lock in a time on the calendar and confirm every detail back digit by digit.",
    icon: CalendarCheck,
    systemPrompt: `You are an appointment setter for [Company Name].

Your job:
- Confirm the caller's name and what they would like to meet about
- Offer two specific time slots and lock in one
- Read back the date, time, and phone number digit by digit to confirm
- End with what they should expect at the appointment

Style:
- Be brief and upbeat: keep each turn short
- If they hesitate, ask what is holding them up instead of pushing
- Never book without reading the details back for confirmation`,
    initialGreeting:
      "Hi! This is [Company Name]. Do you have a minute to lock in a time?",
  },
  {
    id: "reactivator",
    name: "Lead Reactivator",
    blurb: "Re-open cold conversations with value first and gauge renewed intent.",
    icon: RefreshCw,
    systemPrompt: `You are a lead reactivation specialist for [Company Name].

Your job:
- Reference their earlier interest lightly without assuming it is still active
- Lead with value: share a quick market or neighborhood update relevant to them
- Gauge whether their timeline has changed and what would help now
- If interest is back, offer to connect them with an agent today

Style:
- Keep it casual and low pressure: 2-3 sentences per turn
- If they are no longer interested, thank them and close gracefully
- Never claim past details you do not have; ask instead`,
    initialGreeting:
      "Hi! It is [Company Name] checking back in. Have you had a chance to think about your plans?",
  },
  {
    id: "support",
    name: "Customer Support",
    blurb: "Confirm the issue, walk through fixes step by step, escalate when stuck.",
    icon: LifeBuoy,
    systemPrompt: `You are a customer support representative for [Company Name].

Your job:
- Listen, restate the issue in your own words, and confirm you have it right
- Answer questions and walk the caller through fixes one step at a time
- Confirm each step worked before moving on
- Escalate to a human when the issue is unresolved after two attempts or they ask

Style:
- Be patient and reassuring: 2-3 sentences per turn, one question at a time
- Never guess: if you do not know, say you will find out
- Apologize once, then focus on the fix`,
    initialGreeting: "Thanks for calling [Company Name] support. How can I help today?",
  },
  {
    id: "receptionist",
    name: "Receptionist",
    blurb: "Greet every caller, route or take a message, and never invent details.",
    icon: Phone,
    systemPrompt: `You are a professional receptionist for [Company Name].

Your job:
- Greet the caller, identify who they would like to reach, and what it is regarding
- Transfer to the right person when available, otherwise take a clear message
- Offer to book a callback when the person is unavailable
- Repeat back names and phone numbers digit by digit

Style:
- Be calm, polite, and concise: keep turns to 1-2 sentences
- Never invent availability or personal details
- If the caller is upset, acknowledge it and offer a human callback`,
    initialGreeting: "Thank you for calling [Company Name]. How can I direct you?",
  },
];

interface StartingPointStepProps {
  form: UseFormReturn<AgentFormValues>;
  selectedId: string;
  onSelect: (id: string) => void;
}

/** Step 2 — pick a starting point (persona/template) before writing the prompt. */
export function StartingPointStep({ form, selectedId, onSelect }: StartingPointStepProps) {
  const applyPoint = (point: StartingPoint) => {
    form.setValue("systemPrompt", point.systemPrompt);
    form.setValue("initialGreeting", point.initialGreeting);
    onSelect(point.id);
  };

  return (
    <Card>
      <CardContent className="space-y-4 p-6">
        <div className="mb-2">
          <h2 className="text-lg font-medium">Pick a starting point</h2>
          <p className="text-sm text-muted-foreground">
            Choose a persona to prefill a draft prompt, or start blank. You can edit
            everything before creating.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {STARTING_POINTS.map((point) => {
            const PointIcon = point.icon;
            const isSelected = selectedId === point.id;

            return (
              <button
                key={point.id}
                type="button"
                onClick={() => applyPoint(point)}
                className={cn(
                  "flex flex-col rounded-lg border p-4 text-left transition-all hover:border-primary/50",
                  isSelected && "border-primary bg-secondary"
                )}
              >
                <div className="mb-3 flex h-8 w-8 items-center justify-center rounded-md bg-muted">
                  <PointIcon
                    className={cn(
                      "h-4 w-4",
                      isSelected && "text-primary-foreground",
                      !isSelected && "text-muted-foreground"
                    )}
                  />
                </div>
                <span className="font-medium">{point.name}</span>
                <span className="mt-1 text-xs text-muted-foreground">{point.blurb}</span>
              </button>
            );
          })}
        </div>

        <p className="text-xs text-muted-foreground">
          Applying a starter replaces the draft prompt and greeting.
        </p>
      </CardContent>
    </Card>
  );
}
