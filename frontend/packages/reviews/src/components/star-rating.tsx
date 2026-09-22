"use client";

import { Star } from "lucide-react";

import { cn } from "@/lib/utils";

interface StarRatingProps {
  value: number;
  max?: number;
  size?: "sm" | "md" | "lg";
  onChange?: (rating: number) => void;
  className?: string;
}

const sizeMap = {
  sm: "size-4",
  md: "size-6",
  lg: "size-10",
} as const;

export function StarRating({
  value,
  max = 5,
  size = "sm",
  onChange,
  className,
}: StarRatingProps) {
  const interactive = typeof onChange === "function";

  return (
    <div className={cn("flex items-center gap-0.5", className)}>
      {Array.from({ length: max }, (_, i) => i + 1).map((star) => {
        const filled = star <= value;
        const StarIcon = (
          <Star
            className={cn(
              sizeMap[size],
              filled ? "fill-warning text-warning" : "text-muted-foreground/40",
            )}
          />
        );
        if (!interactive) {
          return <span key={star}>{StarIcon}</span>;
        }
        return (
          <button
            key={star}
            type="button"
            aria-label={`${star} star${star === 1 ? "" : "s"}`}
            onClick={() => onChange?.(star)}
            className="cursor-pointer transition-transform hover:scale-110"
          >
            {StarIcon}
          </button>
        );
      })}
    </div>
  );
}
