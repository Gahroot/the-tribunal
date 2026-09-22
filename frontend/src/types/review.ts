// The reviews domain types now live in the extracted `@tribunal/reviews`
// package. Re-export them here so existing `@/types/review` imports keep working
// against a single source of truth.
export type * from "@tribunal/reviews";
