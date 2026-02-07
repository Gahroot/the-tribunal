import type { ReactNode } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";

interface ResourceListSearchProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  placeholder: string;
  filters?: ReactNode;
  wrapInCard?: boolean;
}

export function ResourceListSearch({
  searchQuery,
  onSearchChange,
  placeholder,
  filters,
  wrapInCard = true,
}: ResourceListSearchProps) {
  const content = (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
      <div className="relative flex-1">
        <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder={placeholder}
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          className="pl-10"
        />
      </div>
      {filters && <div className="flex gap-2">{filters}</div>}
    </div>
  );

  if (wrapInCard) {
    return (
      <Card>
        <CardContent className="pt-6">{content}</CardContent>
      </Card>
    );
  }

  return content;
}
