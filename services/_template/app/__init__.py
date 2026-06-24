"""__BLOCK_TITLE__ — Level-3 standalone service (block id: __BLOCK_ID__).

This package is a self-contained FastAPI service: its own app, worker process,
health probes, and OpenAPI surface. The host CRM talks to it over HTTP using a
generated typed client — it never imports this code. See
``docs/blocks/SERVICE_BLOCK_PATTERN.md``.
"""
