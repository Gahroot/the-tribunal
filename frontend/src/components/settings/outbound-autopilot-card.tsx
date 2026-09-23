"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { offersApi } from "@/lib/api/offers";
import { workspacesApi, type AutonomyMandate } from "@/lib/api/workspaces";
import { queryKeys } from "@/lib/query-keys";

function dollars(cents: number): string {
  return `$${Math.round(cents / 100).toLocaleString()}`;
}

function withPatch(mandate: AutonomyMandate, patch: Partial<AutonomyMandate>): AutonomyMandate {
  return { ...mandate, ...patch };
}

export function OutboundAutopilotCard({ workspaceId }: { workspaceId: string }) {
  const queryClient = useQueryClient();

  const { data: mandate, isPending: mandatePending } = useQuery({
    queryKey: queryKeys.settings.autonomyMandate(workspaceId),
    queryFn: () => workspacesApi.getAutonomyMandate(workspaceId),
  });

  const { data: offersData } = useQuery({
    queryKey: queryKeys.offers.all(workspaceId),
    queryFn: () => offersApi.list(workspaceId),
  });

  const activeOffers = (offersData?.items ?? []).filter((offer) => offer.is_active);

  const mutation = useMutation({
    mutationFn: (next: AutonomyMandate) => workspacesApi.updateAutonomyMandate(workspaceId, next),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.settings.autonomyMandate(workspaceId),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.workspaces.detail(workspaceId),
      });
      queryClient.invalidateQueries({
        queryKey: queryKeys.dashboard.todayQueue(workspaceId),
      });
    },
  });

  const save = (patch: Partial<AutonomyMandate>) => {
    if (!mandate) return;
    mutation.mutate(withPatch(mandate, patch));
  };

  const saveQuietHours = (patch: Partial<AutonomyMandate["quiet_hours"]>) => {
    if (!mandate) return;
    mutation.mutate(
      withPatch(mandate, {
        quiet_hours: { ...mandate.quiet_hours, ...patch },
      }),
    );
  };

  const saveOffer = (offerId: string) => {
    if (!mandate) return;
    mutation.mutate(withPatch(mandate, { default_offer_id: offerId }));
  };

  const disabled = mandatePending || mutation.isPending || !mandate;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <CardTitle>Autonomy Mandate</CardTitle>
              {mandate?.posture === "act_and_report" && (
                <Badge variant="secondary">Act & report</Badge>
              )}
            </div>
            <CardDescription>
              Single workspace policy for first-touches, batch-pack closes, daily send caps, quiet
              hours, and human escalation triggers.
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            {mutation.isPending && (
              <Loader2 className="size-4 animate-spin text-muted-foreground" />
            )}
            <Switch
              checked={mandate?.enabled ?? false}
              disabled={disabled}
              onCheckedChange={(enabled) => save({ enabled })}
              aria-label="Toggle autonomy mandate"
            />
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2 rounded-lg border p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <Label>Auto-send first touches</Label>
                <p className="text-xs text-muted-foreground">
                  Launch fresh ad-library outreach without parking a draft for approval.
                </p>
              </div>
              <Switch
                checked={mandate?.auto_send_first_touches ?? false}
                disabled={disabled}
                onCheckedChange={(auto_send_first_touches) => save({ auto_send_first_touches })}
              />
            </div>
          </div>

          <div className="space-y-2 rounded-lg border p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <Label>Auto-close standard packs</Label>
                <p className="text-xs text-muted-foreground">
                  Close 100, 300, 500 anchor, and 1,000 ad packs without human approval.
                </p>
              </div>
              <Switch
                checked={mandate?.auto_close_batch_packs ?? false}
                disabled={disabled}
                onCheckedChange={(auto_close_batch_packs) => save({ auto_close_batch_packs })}
              />
            </div>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <div className="space-y-2 md:col-span-1">
            <Label>Default offer</Label>
            <Select
              value={mandate?.default_offer_id ?? ""}
              onValueChange={saveOffer}
              disabled={disabled || activeOffers.length === 0}
            >
              <SelectTrigger>
                <SelectValue
                  placeholder={
                    activeOffers.length === 0
                      ? "No active offers (create one first)"
                      : "Select an offer"
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {activeOffers.map((offer) => (
                  <SelectItem key={offer.id} value={offer.id}>
                    {offer.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Daily send cap</Label>
            <Input
              type="number"
              min={1}
              max={10000}
              defaultValue={mandate?.daily_send_cap ?? 100}
              disabled={disabled}
              onBlur={(event) => save({ daily_send_cap: Number(event.currentTarget.value || 100) })}
            />
          </div>

          <div className="space-y-2">
            <Label>Max autonomous close</Label>
            <Input
              value={dollars(mandate?.batch_pack_max_price_cents ?? 399700)}
              disabled
              readOnly
            />
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          <div className="flex items-center justify-between gap-3 rounded-lg border p-4">
            <div>
              <Label>Quiet hours</Label>
              <p className="text-xs text-muted-foreground">
                Pause autonomous sends inside this window.
              </p>
            </div>
            <Switch
              checked={mandate?.quiet_hours.enabled ?? true}
              disabled={disabled}
              onCheckedChange={(enabled) => saveQuietHours({ enabled })}
            />
          </div>
          <div className="space-y-2">
            <Label>Quiet start</Label>
            <Input
              type="time"
              defaultValue={mandate?.quiet_hours.start ?? "20:00"}
              disabled={disabled}
              onBlur={(event) => saveQuietHours({ start: event.currentTarget.value })}
            />
          </div>
          <div className="space-y-2">
            <Label>Quiet end</Label>
            <Input
              type="time"
              defaultValue={mandate?.quiet_hours.end ?? "08:00"}
              disabled={disabled}
              onBlur={(event) => saveQuietHours({ end: event.currentTarget.value })}
            />
          </div>
        </div>

        <div className="space-y-2">
          <Label>Allowed autonomous packs</Label>
          <div className="flex flex-wrap gap-2">
            {(mandate?.allowed_batch_packs ?? []).map((pack) => (
              <Badge
                key={pack.pack_key}
                variant={pack.pack_key === mandate?.batch_pack_anchor_key ? "default" : "secondary"}
              >
                {pack.label} / {dollars(pack.price_cents)}
              </Badge>
            ))}
          </div>
        </div>

        <div className="space-y-2">
          <Label>Escalate to human when buyer asks for</Label>
          <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {(mandate?.escalation_rules ?? []).map((rule) => (
              <li key={rule.key}>{rule.label}</li>
            ))}
          </ul>
        </div>

        {mandate?.enabled && !mandate.default_offer_id && (
          <div className="flex items-start gap-2 rounded-lg border bg-background p-3 text-xs text-foreground">
            <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warning" />
            <p>
              Autonomy is on but has no default offer. Morning first-touches will be skipped
              until you pick one.
            </p>
          </div>
        )}
        {mutation.isError && (
          <p className="text-xs text-destructive">
            Couldn&apos;t save autonomy mandate. Please try again.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
