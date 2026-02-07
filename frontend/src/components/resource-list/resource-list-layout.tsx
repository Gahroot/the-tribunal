import type { ReactNode } from "react";

interface ResourceListLayoutProps {
  header: ReactNode;
  stats?: ReactNode;
  filterBar?: ReactNode;
  children: ReactNode;
  emptyState?: ReactNode;
  pagination?: ReactNode;
  extras?: ReactNode;
  isEmpty?: boolean;
}

export function ResourceListLayout({
  header,
  stats,
  filterBar,
  children,
  emptyState,
  pagination,
  extras,
  isEmpty,
}: ResourceListLayoutProps) {
  return (
    <div className="p-6 space-y-6">
      {header}
      {stats}
      {filterBar}
      {isEmpty ? emptyState : children}
      {pagination}
      {extras}
    </div>
  );
}
