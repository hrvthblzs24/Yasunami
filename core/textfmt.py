from __future__ import annotations


class _Safe(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def fill(template: str, **kwargs: object) -> str:
    return str(template).format_map(_Safe(**{k: "" if v is None else v for k, v in kwargs.items()}))
