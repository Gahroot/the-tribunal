"""In-call payment / deposit collection services.

These helpers back the ``collect_payment`` voice tool: they create Stripe
Checkout Sessions for a requested amount (no raw card numbers ever touch the AI
channel), reconcile session status, and notify operators when a caller pays.
"""
