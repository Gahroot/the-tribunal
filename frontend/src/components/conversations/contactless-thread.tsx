// Keep the existing inbox entry point; the exact-thread renderer is shared with
// ConversationFeed so contact-linked and unknown-number threads behave alike.
export { InboxThread as ContactlessThread } from "@/components/conversation/inbox-thread";
export type { InboxThreadProps as ContactlessThreadProps } from "@/components/conversation/inbox-thread";
