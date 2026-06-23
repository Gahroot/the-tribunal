// Presentational stats row for the Automations page.
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export interface AutomationStatsProps {
  totalCount: number;
  activeCount: number;
  triggeredToday: number;
  isLoading: boolean;
}

export function AutomationStats({
  totalCount,
  activeCount,
  triggeredToday,
  isLoading,
}: AutomationStatsProps) {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      <Card>
        <CardHeader className="pb-2">
          <CardDescription>Total Automations</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {isLoading ? <Skeleton className="h-8 w-8" /> : totalCount}
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardDescription>Active</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold text-success">
            {isLoading ? <Skeleton className="h-8 w-8" /> : activeCount}
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-2">
          <CardDescription>Triggered Today</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">
            {isLoading ? <Skeleton className="h-8 w-8" /> : triggeredToday}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
