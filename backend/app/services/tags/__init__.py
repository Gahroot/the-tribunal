"""Tag services."""

from .tag_repository import (
    bulk_add_tags,
    bulk_remove_tags,
    create_tag,
    delete_tag,
    get_tag_by_id,
    get_tags_for_contact,
    list_tags,
    update_tag,
)
from .tag_service import TagService

__all__ = [
    "TagService",
    "list_tags",
    "get_tag_by_id",
    "create_tag",
    "update_tag",
    "delete_tag",
    "bulk_add_tags",
    "bulk_remove_tags",
    "get_tags_for_contact",
]
