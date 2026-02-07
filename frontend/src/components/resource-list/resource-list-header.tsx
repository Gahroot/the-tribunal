import type { ReactNode } from "react";

interface ResourceListHeaderProps {
  title: string;
  subtitle: string;
  action: ReactNode;
}

export function ResourceListHeader({ title, subtitle, action }: ResourceListHeaderProps) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        <p className="text-muted-foreground">{subtitle}</p>
      </div>
      {action}
    </div>
  );
}
