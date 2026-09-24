"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useWorkspaceId } from "@/hooks/useWorkspaceId";
import { campaignReportsApi, type AttemptFunnelMetrics } from "@/lib/api/campaign-reports";
import { queryKeys } from "@/lib/query-keys";

type Slice = "attempt" | "hour_utc" | "lead_source" | "campaign";
const slices: Array<{ value: Slice; label: string }> = [
  { value: "attempt", label: "Attempt number" },
  { value: "hour_utc", label: "Hour (UTC)" },
  { value: "lead_source", label: "Lead source" },
  { value: "campaign", label: "Campaign" },
];
const pct = (value: number) => `${(value * 100).toFixed(1)}%`;
const usd = (value: number | null) => value === null ? "—" : `$${value.toFixed(2)}`;

function labelFor(row: { value: number | string; campaign_name?: string }, slice: Slice) {
  if (slice === "hour_utc") return `${String(row.value).padStart(2, "0")}:00`;
  if (slice === "attempt") return `#${row.value}`;
  if (slice === "campaign") return row.campaign_name || String(row.value);
  return String(row.value);
}

export function AttemptFunnelPanel() {
  const workspaceId = useWorkspaceId();
  const [slice, setSlice] = useState<Slice>("attempt");
  const [days, setDays] = useState(30);
  const { data, isPending, isError, refetch } = useQuery({
    queryKey: queryKeys.campaignReports.attemptFunnel(workspaceId ?? "", days),
    queryFn: () => campaignReportsApi.attemptFunnel(workspaceId!, days),
    enabled: !!workspaceId,
  });
  const rows = data?.[slice] as Array<AttemptFunnelMetrics & { value: number | string; campaign_name?: string }> | undefined;

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
        <CardTitle>Voice attempt funnel</CardTitle>
        <div className="flex flex-wrap gap-3">
          <label className="text-sm">Period{" "}
            <select className="rounded-md border bg-background px-3 py-2 text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2" value={days} onChange={(event) => setDays(Number(event.target.value))}>
              <option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option>
            </select>
          </label>
          <label className="text-sm">Break down by{" "}
            <select className="rounded-md border bg-background px-3 py-2 text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2" value={slice} onChange={(event) => setSlice(event.target.value as Slice)}>
              {slices.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}
            </select>
          </label>
        </div>
      </CardHeader>
      <CardContent>
        {isPending ? <p role="status">Loading call evidence…</p> : isError ? (
          <div role="alert">Call evidence is unavailable. <button className="underline" type="button" onClick={() => void refetch()}>Retry</button></div>
        ) : !data || !rows?.length ? <p>No voice calls in this period.</p> : (
          <>
            <p className="mb-3 text-sm text-muted-foreground">
              {data.overall.calls} calls · {data.overall.booked} booked · {data.overall.shown} shown · estimated {usd(data.overall.estimated_cost_per_call_usd)} per call. Rates use calls as the denominator; show rate uses booked appointments. Costs use a blended estimate, not a Telnyx invoice.
            </p>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[850px] text-left text-sm">
                <caption className="sr-only">Voice call funnel by {slices.find((item) => item.value === slice)?.label}, {days} days, hours in UTC</caption>
                <thead><tr className="border-b text-muted-foreground">
                  <th scope="col" className="p-2">{slices.find((item) => item.value === slice)?.label}</th>
                  <th scope="col" className="p-2">Calls</th>
                  <th scope="col" className="p-2">Connect</th>
                  <th scope="col" className="p-2">Conversation</th>
                  <th scope="col" className="p-2">Qualified</th>
                  <th scope="col" className="p-2">Booked</th>
                  <th scope="col" className="p-2">Shown</th>
                  <th scope="col" className="p-2">Show / booked</th>
                  <th scope="col" className="p-2">Cost / booked</th>
                  <th scope="col" className="p-2">Cost / shown</th>
                </tr></thead>
                <tbody>{rows.map((row) => <tr className="border-b" key={row.value}>
                  <th scope="row" className="p-2 font-medium">{labelFor(row, slice)}</th>
                  <td className="p-2">{row.calls}</td>
                  <td className="p-2">{row.connected} ({pct(row.connect_rate)})</td>
                  <td className="p-2">{row.conversations} ({pct(row.conversation_rate)})</td>
                  <td className="p-2">{row.qualified} ({pct(row.qualified_rate)})</td>
                  <td className="p-2">{row.booked} ({pct(row.booked_rate)})</td>
                  <td className="p-2">{row.shown} ({pct(row.shown_rate)})</td>
                  <td className="p-2">{row.show_rate_of_booked === null ? "—" : pct(row.show_rate_of_booked)}</td>
                  <td className="p-2">{usd(row.estimated_cost_per_booked_usd)}</td>
                  <td className="p-2">{usd(row.estimated_cost_per_shown_usd)}</td>
                </tr>)}</tbody>
              </table>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
