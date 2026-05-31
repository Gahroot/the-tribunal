"""Regression tests for Alembic model registration."""

from __future__ import annotations

import importlib.util
import pkgutil
from types import ModuleType

from sqlalchemy import inspect
from sqlalchemy.orm import DeclarativeBase

from app.db.model_registry import (
    DEFAULT_MODELS_PACKAGE,
    import_model_modules,
    iter_model_module_names,
)


def _expected_model_tables(modules: tuple[ModuleType, ...]) -> set[str]:
    table_names: set[str] = set()
    for module in modules:
        for value in vars(module).values():
            is_declarative_model = (
                isinstance(value, type)
                and issubclass(value, DeclarativeBase)
                and value is not DeclarativeBase
            )
            if is_declarative_model:
                mapper = inspect(value, raiseerr=False)
                if mapper is not None:
                    table_names.add(mapper.local_table.name)
    return table_names


def test_import_model_modules_registers_every_model_table() -> None:
    """Every app.models module should contribute its declarative tables to metadata."""
    modules = import_model_modules()

    from app.db.base import Base

    expected_tables = _expected_model_tables(modules)

    assert expected_tables
    assert Base.metadata.tables.keys() >= expected_tables


def test_iter_model_module_names_finds_all_model_files() -> None:
    """New model files should be discovered without updating a manual import list."""
    spec = importlib.util.find_spec(DEFAULT_MODELS_PACKAGE)
    assert spec is not None
    assert spec.submodule_search_locations is not None

    discovered_modules = iter_model_module_names()
    package_modules = tuple(
        sorted(
            module_info.name
            for module_info in pkgutil.iter_modules(
                spec.submodule_search_locations,
                f"{DEFAULT_MODELS_PACKAGE}.",
            )
            if not module_info.ispkg
            and not module_info.name.rsplit(".", maxsplit=1)[-1].startswith("_")
        )
    )

    assert discovered_modules == package_modules
