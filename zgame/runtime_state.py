"""Centralized accessors for runtime scratch state and META."""

from __future__ import annotations

from typing import Any


class RuntimeProxy:
    def __init__(self, game):
        object.__setattr__(self, "_game", game)

    def _raw_key(self, key: str) -> str:
        return str(key)

    def get(self, key: str, default: Any = None) -> Any:
        return self._game.__dict__.get(self._raw_key(key), default)

    def pop(self, key: str, default: Any = None) -> Any:
        return self._game.__dict__.pop(self._raw_key(key), default)

    def setdefault(self, key: str, default: Any = None) -> Any:
        return self._game.__dict__.setdefault(self._raw_key(key), default)

    def clear(self, *keys: str) -> None:
        for key in keys:
            self._game.__dict__.pop(self._raw_key(key), None)

    def __contains__(self, key: str) -> bool:
        return self._raw_key(key) in self._game.__dict__

    def __getitem__(self, key: str) -> Any:
        return self._game.__dict__[self._raw_key(key)]

    def __setitem__(self, key: str, value: Any) -> None:
        self._game.__dict__[self._raw_key(key)] = value

    def __getattr__(self, key: str) -> Any:
        return self._game.__dict__.get(self._raw_key(key))

    def __setattr__(self, key: str, value: Any) -> None:
        if key == "_game":
            object.__setattr__(self, key, value)
            return
        self._game.__dict__[self._raw_key(key)] = value

    def to_dict(self) -> dict[str, Any]:
        return dict(self._game.__dict__)


class MetaProxy:
    def __init__(self, game):
        self._game = game

    def get(self, key: str, default: Any = None) -> Any:
        return self._game.META.get(key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(self._game.META.get(key, default))
        except Exception:
            return int(default)

    def get_float(self, key: str, default: float = 0.0) -> float:
        try:
            return float(self._game.META.get(key, default))
        except Exception:
            return float(default)

    def get_bool(self, key: str, default: bool = False) -> bool:
        try:
            return bool(self._game.META.get(key, default))
        except Exception:
            return bool(default)

    def update(self, *args, **kwargs) -> None:
        self._game.META.update(*args, **kwargs)

    def setdefault(self, key: str, default: Any = None) -> Any:
        return self._game.META.setdefault(key, default)

    def items(self):
        return self._game.META.items()

    def keys(self):
        return self._game.META.keys()

    def to_dict(self) -> dict[str, Any]:
        return dict(self._game.META)

    def __contains__(self, key: str) -> bool:
        return key in self._game.META

    def __getitem__(self, key: str) -> Any:
        return self._game.META[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._game.META[key] = value


def runtime(game) -> RuntimeProxy:
    proxy = game.__dict__.get("_runtime_proxy")
    if not isinstance(proxy, RuntimeProxy):
        proxy = RuntimeProxy(game)
        game.__dict__["_runtime_proxy"] = proxy
    return proxy


def meta(game) -> MetaProxy:
    proxy = game.__dict__.get("_meta_proxy")
    if not isinstance(proxy, MetaProxy):
        proxy = MetaProxy(game)
        game.__dict__["_meta_proxy"] = proxy
    return proxy
