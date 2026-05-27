from __future__ import annotations

import logging
from importlib import import_module
from typing import Callable, Generic, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)


class Registry(Generic[T]):
    """Small named registry used for framework extension points.

    A registry lets configuration refer to a stable string key while Python code
    provides the actual object. This keeps the runtime open for extension
    without hard-coding every capability, assistant, or future workflow.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._items: dict[str, T] = {}

    def register(self, key: str, value: T) -> T:
        if key in self._items:
            logger.error("registry key already exists", extra={"registry": self.name, "key": key})
            raise ValueError(f"{self.name} already contains '{key}'")
        self._items[key] = value
        logger.debug("registered item", extra={"registry": self.name, "key": key})
        return value

    def decorator(self, key: str) -> Callable[[T], T]:
        def _register(value: T) -> T:
            return self.register(key, value)

        return _register

    def get(self, key: str) -> T:
        try:
            return self._items[key]
        except KeyError as exc:
            logger.error("registry key missing", extra={"registry": self.name, "key": key})
            raise KeyError(f"{self.name} does not contain '{key}'") from exc

    def maybe_get(self, key: str) -> T | None:
        return self._items.get(key)

    def keys(self) -> list[str]:
        return sorted(self._items)


def import_path(path: str) -> object:
    """Import `module:attribute` paths used by plugin-like config entries."""
    module_name, _, attr_name = path.partition(":")
    if not module_name or not attr_name:
        logger.error("invalid import path", extra={"import_path": path})
        raise ValueError(f"import path must look like 'module:attribute', got '{path}'")
    logger.debug(
        "importing configured path",
        extra={"module_name": module_name, "attribute_name": attr_name},
    )
    module = import_module(module_name)
    return getattr(module, attr_name)
