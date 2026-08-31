from __future__ import annotations

_REGISTRY: dict[tuple[str, str], type] = {}


def register(kind: str, name: str):
    def deco(cls):
        _REGISTRY[(kind, name)] = cls
        return cls
    return deco


def build(kind: str, name: str, **kwargs):
    key = (kind, name)
    if key not in _REGISTRY:
        raise KeyError(f"no {kind} registered under name '{name}'")
    return _REGISTRY[key](**kwargs)


def available(kind: str) -> list[str]:
    return sorted(name for k, name in _REGISTRY if k == kind)
