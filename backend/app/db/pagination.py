"""Pagination utilities for SQLAlchemy async queries."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class PaginationResult[T]:
    """Result of a paginated query."""

    items: Sequence[T]
    total: int
    page: int
    page_size: int
    pages: int


async def paginate(
    db: AsyncSession,
    query: Select[tuple[Any, ...]],
    page: int = 1,
    page_size: int = 50,
) -> PaginationResult[Any]:
    """Execute a paginated query and return results with metadata."""
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Apply pagination
    paginated_query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(paginated_query)
    items = result.scalars().all()

    # Calculate pages
    pages = (total + page_size - 1) // page_size if total > 0 else 1

    return PaginationResult(
        items=items, total=total, page=page, page_size=page_size, pages=pages
    )


async def paginate_unique(
    db: AsyncSession,
    query: Select[tuple[Any, ...]],
    page: int = 1,
    page_size: int = 50,
) -> PaginationResult[Any]:
    """Paginate with unique() for queries with joins/eager loading."""
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    paginated_query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(paginated_query)
    items = result.unique().scalars().all()

    pages = (total + page_size - 1) // page_size if total > 0 else 1

    return PaginationResult(
        items=items, total=total, page=page, page_size=page_size, pages=pages
    )
