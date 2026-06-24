# Host client for the `__BLOCK_ID__` service

This folder is the **host CRM's** integration surface for the
`__BLOCK_ID__` service. It is *not* run inside the service.

## Typed client generation (recommended)

The service exposes `/openapi.json`. Generate a typed client against it and check
it into the host, mirroring how the frontend consumes the backend's OpenAPI:

```
# Frontend today (for reference):
openapi-typescript ../backend/openapi.json -o src/lib/api/_generated.ts

# Host -> service: generate a typed Python client from the service schema, e.g.
openapi-python-client update --url <service-url>/openapi.json --overwrite
```

Treat the generated client like `frontend/src/lib/api/_generated.ts`: check it in,
fail CI on drift, and call the service **only** through the generated types so a
service API change becomes a host-side compile error before deploy.

## Auth on every call

Every host → service request carries an `Authorization: Bearer <service-token>`
header. Mint the token with the host's existing JWT helpers in
`backend/app/core/security.py`, adding a `type: "service"` claim and the
service's block id as `aud`:

```python
# on the host
from datetime import UTC, datetime, timedelta
import jwt
from app.core.config import settings

def mint_service_token(workspace_id: int) -> str:
    payload = {
        "type": "service",
        "aud": "__BLOCK_ID__",
        "workspace_id": str(workspace_id),
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
```

The service verifies signature + `aud` + expiry + `type == "service"` (see
`app/security.py` in the service).

## Receiving events from the service

The service POSTs signed outcomes to the host at `HOST_EVENT_WEBHOOK_PATH`. On
the host, add a receiver that verifies the HMAC-SHA256 `timestamp|body` signature
using the shared secret, exactly like the Cal.com webhook verifier in
`backend/app/core/webhook_security.py`. Process events idempotently (key on the
event id) via `app.core_api`'s `derive_webhook_delivery_key`.
