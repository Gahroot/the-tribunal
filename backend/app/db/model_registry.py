"""Utilities for importing SQLAlchemy model modules."""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil
from types import ModuleType

DEFAULT_MODELS_PACKAGE = "app.models"


class ModelRegistryError(RuntimeError):
    """Raised when model module discovery or import fails."""


def iter_model_module_names(package_name: str = DEFAULT_MODELS_PACKAGE) -> tuple[str, ...]:
    """Return importable model module names for a models package."""
    spec = importlib.util.find_spec(package_name)
    if spec is None or spec.submodule_search_locations is None:
        raise ModelRegistryError(f"Could not find model package {package_name!r}")

    module_names = [
        module_info.name
        for module_info in pkgutil.iter_modules(
            spec.submodule_search_locations,
            f"{package_name}.",
        )
        if not module_info.ispkg
        and not module_info.name.rsplit(".", maxsplit=1)[-1].startswith("_")
    ]
    return tuple(sorted(module_names))


def import_model_modules(package_name: str = DEFAULT_MODELS_PACKAGE) -> tuple[ModuleType, ...]:
    """Import every model module so declarative tables are registered in metadata."""
    modules: list[ModuleType] = []
    for module_name in iter_model_module_names(package_name):
        try:
            modules.append(importlib.import_module(module_name))
        except Exception as exc:
            raise ModelRegistryError(
                f"Could not import SQLAlchemy model module {module_name!r}"
            ) from exc
    return tuple(modules)
