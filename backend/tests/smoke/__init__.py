"""Live-deployment smoke tests.

Unlike the rest of the suite (which runs against an in-process ASGI app and a
local test database), these tests fire real HTTP requests at a *deployed*
backend to prove it is up and correctly wired. They are skipped unless
``SMOKE_BASE_URL`` points at the target environment.
"""
