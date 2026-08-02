#!/usr/bin/env python3
"""Validate locale JSON structure, parity, placeholders, and report unused keys."""

from __future__ import annotations
import ast
import json
from pathlib import Path
from string import Formatter

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "src/webcamcctv/locales"


def load(path: Path) -> dict[str, str]:
    duplicates = []

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                duplicates.append(key)
            result[key] = value
        return result

    data = json.loads(path.read_text("utf-8"), object_pairs_hook=pairs)
    if duplicates:
        raise ValueError(f"{path}: duplicate keys: {', '.join(duplicates)}")
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in data.items()
    ):
        raise ValueError(f"{path}: all keys and values must be strings")
    return data


def fields(value: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(value) if name}


def main() -> int:
    resources = {p.stem: load(p) for p in sorted(LOCALES.glob("*.json"))}
    base = resources["en"]
    errors = []
    for locale, data in resources.items():
        missing = sorted(set(base) - set(data))
        extra = sorted(set(data) - set(base))
        if missing:
            errors.append(f"{locale}: missing: {', '.join(missing)}")
        if extra:
            errors.append(f"{locale}: extra: {', '.join(extra)}")
        for key in set(base) & set(data):
            if fields(base[key]) != fields(data[key]):
                errors.append(
                    f"{locale}: placeholder mismatch for {key}: {fields(base[key])} != {fields(data[key])}"
                )
    used = set()
    dynamic_prefixes = ("service.", "event.", "format.duration_")
    source_paths = list((ROOT / "src").rglob("*.py")) + list((ROOT / "packaging").rglob("*.py"))
    for path in source_paths:
        tree = ast.parse(path.read_text("utf-8"), filename=str(path))
        for node in ast.walk(tree):
            # Count stable keys passed directly or stored in declarative key tables.
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in base
            ):
                used.add(node.value)
    unused = sorted(
        key
        for key in base
        if key not in used and key != "meta.language_name" and not key.startswith(dynamic_prefixes)
    )
    print(
        json.dumps(
            {"locales": sorted(resources), "keys": len(base), "unused": unused, "errors": errors},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
