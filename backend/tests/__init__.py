"""Pytest test root package.

Presence of this file forces pytest into ``rootdir``-based path resolution
(adds ``backend/`` to ``sys.path`` rather than ``tests/``), preventing the
``tests/websockets/`` sibling directory from shadowing the third-party
``websockets`` package during collection. Without it, any test that imports
``app.services.ai.elevenlabs_tts`` (which imports ``websockets.asyncio``)
fails to collect because Python resolves ``websockets`` to
``tests/websockets/`` first.
"""
