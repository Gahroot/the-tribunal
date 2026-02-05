"""Segment services."""

from .segment_repository import (
    create_segment,
    delete_segment,
    get_segment_by_id,
    list_segments,
    resolve_segment_contacts,
    update_segment,
)
from .segment_service import SegmentService

__all__ = [
    "SegmentService",
    "list_segments",
    "get_segment_by_id",
    "create_segment",
    "update_segment",
    "delete_segment",
    "resolve_segment_contacts",
]
