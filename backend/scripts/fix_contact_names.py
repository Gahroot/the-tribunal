#!/usr/bin/env python
"""Fix contact names by splitting first and last names.

This script finds contacts where both first and last names are in the first_name
field and splits them properly into first_name and last_name fields.

Usage:
    cd backend && uv run python scripts/fix_contact_names.py

    # To run for a specific workspace:
    cd backend && uv run python scripts/fix_contact_names.py --workspace-name "Marian Grout Real Estate"
"""

import argparse
import asyncio
import re
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.contact import Contact
from app.models.workspace import Workspace


def split_full_name(full_name: str) -> tuple[str, str | None]:
    """Split a full name into first and last name.

    Args:
        full_name: The full name to split

    Returns:
        Tuple of (first_name, last_name). Last name can be None if only one name.
    """
    # Strip and normalize whitespace
    full_name = re.sub(r'\s+', ' ', full_name.strip())

    if not full_name:
        return ("Unknown", None)

    # Split by space
    parts = full_name.split(' ', 1)

    if len(parts) == 1:
        # Only one name, treat as first name
        return (parts[0], None)
    else:
        # Two or more parts, first is first_name, rest is last_name
        return (parts[0], parts[1])


async def fix_workspace_contacts(
    session: AsyncSession,
    workspace_id: str,
    dry_run: bool = True
) -> tuple[int, int]:
    """Fix contact names for a specific workspace.

    Args:
        session: Database session
        workspace_id: Workspace UUID
        dry_run: If True, only show what would be changed without updating

    Returns:
        Tuple of (total_contacts, fixed_contacts)
    """
    # Query all contacts in the workspace
    stmt = select(Contact).where(Contact.workspace_id == workspace_id)
    result = await session.execute(stmt)
    contacts = result.scalars().all()

    total_contacts = len(contacts)
    fixed_contacts = 0

    print(f"\nFound {total_contacts} contacts in workspace")
    print("=" * 80)

    for contact in contacts:
        # Check if contact needs fixing:
        # - first_name contains a space (likely has last name in it)
        # - last_name is empty or None
        needs_fixing = ' ' in contact.first_name and not contact.last_name

        if needs_fixing:
            old_first = contact.first_name
            old_last = contact.last_name or "(empty)"

            # Split the name
            new_first, new_last = split_full_name(contact.first_name)

            print(f"\nContact ID: {contact.id}")
            print(f"  Phone: {contact.phone_number}")
            print(f"  Current: '{old_first}' | '{old_last}'")
            print(f"  New:     '{new_first}' | '{new_last or '(empty)'}'")

            if not dry_run:
                contact.first_name = new_first
                contact.last_name = new_last
                fixed_contacts += 1
            else:
                fixed_contacts += 1

    if not dry_run and fixed_contacts > 0:
        await session.commit()
        print(f"\n✓ Updated {fixed_contacts} contacts")
    elif fixed_contacts > 0:
        print(f"\n[DRY RUN] Would update {fixed_contacts} contacts")
        print("Run with --apply to make these changes")
    else:
        print("\n✓ No contacts need fixing")

    return total_contacts, fixed_contacts


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Fix contact names by splitting them properly")
    parser.add_argument(
        "--workspace-name",
        type=str,
        default="Marian Grout Real Estate",
        help="Name of the workspace to fix (default: 'Marian Grout Real Estate')"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply the changes (default is dry-run mode)"
    )

    args = parser.parse_args()

    print("=" * 80)
    print("Contact Name Splitter")
    print("=" * 80)
    print(f"Workspace: {args.workspace_name}")
    print(f"Mode: {'APPLY CHANGES' if args.apply else 'DRY RUN'}")
    print("=" * 80)

    # Create async engine
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        # Find the workspace
        stmt = select(Workspace).where(Workspace.name.ilike(f"%{args.workspace_name}%"))
        result = await session.execute(stmt)
        workspace = result.scalar_one_or_none()

        if not workspace:
            print(f"\nERROR: Workspace '{args.workspace_name}' not found")
            print("\nAvailable workspaces:")
            stmt = select(Workspace)
            result = await session.execute(stmt)
            workspaces = result.scalars().all()
            for ws in workspaces:
                print(f"  - {ws.name} (ID: {ws.id})")
            sys.exit(1)

        print(f"\nFound workspace: {workspace.name} (ID: {workspace.id})")

        # Fix contacts in this workspace
        total, fixed = await fix_workspace_contacts(
            session,
            str(workspace.id),
            dry_run=not args.apply
        )

        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total contacts:    {total}")
        print(f"Contacts fixed:    {fixed}")
        print(f"Unchanged:         {total - fixed}")

        if not args.apply and fixed > 0:
            print("\n⚠️  This was a DRY RUN - no changes were made")
            print("   Run again with --apply to make the changes")
        elif fixed > 0:
            print("\n✓ Changes applied successfully!")

        print()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
