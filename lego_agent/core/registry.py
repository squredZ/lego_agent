from __future__ import annotations

from importlib import import_module
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    def __init__(self, name: str) -> None:
        self.name = name
        self._items: dict[str, T] = {}

    def register(self, key: str, value: T) -> T:
        if key in self._items:
            raise ValueError(f"{self.name} already contains '{key}'")
        self._items[key] = value
        return value

    def decorator(self, key: str) -> Callable[[T], T]:
        def _register(value: T) -> T:
            return self.register(key, value)

        return _register

    def get(self, key: str) -> T:
        try:
            return self._items[key]
        except KeyError as exc:
            raise KeyError(f"{self.name} does not contain '{key}'") from exc

    def maybe_get(self, key: str) -> T | None:
        return self._items.get(key)

    def keys(self) -> list[str]:
        return sorted(self._items)


def import_path(path: str) -> object:
    module_name, _, attr_name = path.partition(":")
    if not module_name or not attr_name:
        raise ValueError(f"import path must look like 'module:attribute', got '{path}'")
    module = import_module(module_name)
    return getattr(module, attr_name)
