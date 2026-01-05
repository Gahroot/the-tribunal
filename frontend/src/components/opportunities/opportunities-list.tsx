"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { opportunitiesApi } from "@/lib/api/opportunities";

interface OpportunitiesListProps {
  workspaceId: string;
}

function formatCurrency(amount: number | undefined, currency: string) {
  if (!amount) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency,
  }).format(amount);
}

function getStageColor(probability: number): string {
  if (probability === 0) return "bg-red-100 text-red-800";
  if (probability < 50) return "bg-yellow-100 text-yellow-800";
  if (probability < 100) return "bg-blue-100 text-blue-800";
  return "bg-green-100 text-green-800";
}

function getStatusColor(status: string): string {
  switch (status) {
    case "won":
      return "bg-green-100 text-green-800";
    case "lost":
      return "bg-red-100 text-red-800";
    case "abandoned":
      return "bg-gray-100 text-gray-800";
    default:
      return "bg-blue-100 text-blue-800";
  }
}

export function OpportunitiesList({ workspaceId }: OpportunitiesListProps) {
  const [page] = React.useState(1);
  const [search] = React.useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["opportunities", workspaceId, page, search],
    queryFn: () =>
      opportunitiesApi.list(workspaceId, {
        page,
        page_size: 50,
        search: search || undefined,
      }),
    enabled: !!workspaceId,
  });

  if (isLoading) {
    return (
      <div className="w-full h-full p-4 overflow-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Amount</TableHead>
              <TableHead>Probability</TableHead>
              <TableHead>Close Date</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {Array.from({ length: 10 }).map((_, i) => (
              <TableRow key={i}>
                <TableCell>
                  <Skeleton className="h-4 w-48" />
                </TableCell>
                <TableCell>
                  <Skeleton className="h-4 w-24" />
                </TableCell>
                <TableCell>
                  <Skeleton className="h-4 w-16" />
                </TableCell>
                <TableCell>
                  <Skeleton className="h-4 w-20" />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    );
  }

  return (
    <div className="w-full h-full overflow-auto">
      <Table>
        <TableHeader className="sticky top-0 bg-background">
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Amount</TableHead>
            <TableHead>Probability</TableHead>
            <TableHead>Expected Close</TableHead>
            <TableHead>Source</TableHead>
            <TableHead>Created</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data?.items && data.items.length > 0 ? (
            data.items.map((opportunity) => (
              <TableRow key={opportunity.id} className="hover:bg-muted/50">
                <TableCell className="font-medium">{opportunity.name}</TableCell>
                <TableCell>
                  <Badge className={getStatusColor(opportunity.status)}>
                    {opportunity.status}
                  </Badge>
                </TableCell>
                <TableCell>{formatCurrency(opportunity.amount, opportunity.currency)}</TableCell>
                <TableCell>
                  <Badge className={getStageColor(opportunity.probability)}>
                    {opportunity.probability}%
                  </Badge>
                </TableCell>
                <TableCell>
                  {opportunity.expected_close_date
                    ? new Date(opportunity.expected_close_date).toLocaleDateString()
                    : "—"}
                </TableCell>
                <TableCell>{opportunity.source || "—"}</TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {new Date(opportunity.created_at).toLocaleDateString()}
                </TableCell>
              </TableRow>
            ))
          ) : (
            <TableRow>
              <TableCell colSpan={7} className="text-center text-muted-foreground py-8">
                No opportunities found
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
