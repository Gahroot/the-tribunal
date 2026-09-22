"""Canonical ``core`` import surface for every other block.

This package is the single documented facade that all non-core blocks import
core primitives from — workspace scoping, DB session + pagination, auth/DI
dependencies, config/secrets, the Fernet credential vault, idempotency-key
derivation, the background-worker base class, and the automation event bus.

Blocks MUST NOT reach into the underlying internal modules (``app.api.deps``,
``app.db.*``, ``app.core.*``, ``app.services.idempotency``,
``app.workers.base``, ``app.services.automations.events``) directly. Those are
private to the core block; this module re-exports their real public names.

See ``README.md`` in this package for the policy and the rationale.
"""

from __future__ import annotations

# --- DI / auth (app.api.deps) -------------------------------------------------
from app.api.deps import (
    DB,
    ActiveUser,
    CurrentMembership,
    CurrentUser,
    OptionalCurrentUser,
    TransactionalDB,
    WorkspaceAccess,
    WorkspaceAdminAccess,
    get_current_active_user,
    get_current_user,
    get_membership,
    get_optional_current_user,
    get_workspace,
    get_workspace_admin,
)

# --- Config / secrets (app.core.config) --------------------------------------
from app.core.config import Settings, get_settings, settings

# --- Encryption / credential vault (app.core.encryption) ----------------------
from app.core.encryption import (
    EncryptedString,
    InvalidToken,
    LookupHash,
    decrypt_json,
    encrypt_json,
    hash_phone,
    hash_value,
    hash_value_or_none,
)

# --- Pagination (app.db.pagination) ------------------------------------------
from app.db.pagination import (
    PaginationResult,
    list_response,
    paginate,
    paginate_rows,
)

# --- Tenancy / workspace scoping (app.db.scope) ------------------------------
from app.db.scope import (
    apply_workspace_scope,
    assert_workspace_owned,
    get_workspace_owned,
    select_workspace_owned,
)

# --- DB session (app.db.session) ---------------------------------------------
from app.db.session import (
    AsyncSessionLocal,
    get_db,
    transaction_boundary,
)

# --- Automation event bus (app.services.automations.events) -------------------
from app.services.automations.events import (
    AUTOMATION_EVENT_TRIGGERS,
    EVENT_DEAL_STAGE_CHANGED,
    EVENT_KNOWLEDGE_DOCUMENT_UPLOADED,
    EVENT_MISSED_CALL,
    EVENT_OPPORTUNITY_CREATED,
    EVENT_REVIEW_RECEIVED,
    EVENT_REVIEW_REQUEST_RESPONSE,
    EVENT_ROLEPLAY_COMPLETED,
    emit_automation_event,
)

# --- Idempotency (app.services.idempotency) ----------------------------------
from app.services.idempotency import (
    DEFAULT_IDEMPOTENCY_HEADER,
    DEFAULT_WEBHOOK_IDEMPOTENCY_TTL_SECONDS,
    OUTBOUND_IDEMPOTENCY_NAMESPACE,
    MessageIdempotencyState,
    RedisIdempotencyClaim,
    claim_redis_idempotency_key,
    derive_outbound_key,
    derive_webhook_delivery_key,
    derive_worker_retry_key,
    encode_client_state,
    idempotency_headers,
    resolve_message_idempotency,
)

# --- Worker runtime (app.workers.base / app.workers.retryable) ----------------
from app.workers.base import BaseWorker, WorkerRegistry
from app.workers.retryable import RetryableWorker

__all__ = [
    # DI / auth
    "ActiveUser",
    "CurrentMembership",
    "CurrentUser",
    "DB",
    "OptionalCurrentUser",
    "TransactionalDB",
    "WorkspaceAccess",
    "WorkspaceAdminAccess",
    "get_current_active_user",
    "get_current_user",
    "get_membership",
    "get_optional_current_user",
    "get_workspace",
    "get_workspace_admin",
    # Config / secrets
    "Settings",
    "get_settings",
    "settings",
    # Encryption / credential vault
    "EncryptedString",
    "InvalidToken",
    "LookupHash",
    "decrypt_json",
    "encrypt_json",
    "hash_phone",
    "hash_value",
    "hash_value_or_none",
    # Pagination
    "PaginationResult",
    "list_response",
    "paginate",
    "paginate_rows",
    # Tenancy / workspace scoping
    "apply_workspace_scope",
    "assert_workspace_owned",
    "get_workspace_owned",
    "select_workspace_owned",
    # DB session
    "AsyncSessionLocal",
    "get_db",
    "transaction_boundary",
    # Automation event bus
    "AUTOMATION_EVENT_TRIGGERS",
    "EVENT_DEAL_STAGE_CHANGED",
    "EVENT_KNOWLEDGE_DOCUMENT_UPLOADED",
    "EVENT_MISSED_CALL",
    "EVENT_OPPORTUNITY_CREATED",
    "EVENT_REVIEW_RECEIVED",
    "EVENT_REVIEW_REQUEST_RESPONSE",
    "EVENT_ROLEPLAY_COMPLETED",
    "emit_automation_event",
    # Idempotency
    "DEFAULT_IDEMPOTENCY_HEADER",
    "DEFAULT_WEBHOOK_IDEMPOTENCY_TTL_SECONDS",
    "OUTBOUND_IDEMPOTENCY_NAMESPACE",
    "MessageIdempotencyState",
    "RedisIdempotencyClaim",
    "claim_redis_idempotency_key",
    "derive_outbound_key",
    "derive_webhook_delivery_key",
    "derive_worker_retry_key",
    "encode_client_state",
    "idempotency_headers",
    "resolve_message_idempotency",
    # Worker runtime
    "BaseWorker",
    "WorkerRegistry",
    "RetryableWorker",
]
