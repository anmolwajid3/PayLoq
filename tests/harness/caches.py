"""Module-level caches the harness clears before every generation.

The registry is the complete list discovered in product code. A new
``lru_cache`` / ``functools.cache`` or module-level ``_engine`` singleton
fails the harness until it is added here and cleared.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCAN_ROOTS = ("packages", "apps")

# file, line, symbol. Line is the decorator or the assignment, not the def.
KNOWN_CACHES: tuple[tuple[str, int, str], ...] = (
    ("apps/api/src/payloq_api/config.py", 53, "get_settings"),
    ("apps/api/src/payloq_api/db.py", 11, "_engine"),
    ("packages/schemas/src/payloq_schemas/field_map.py", 60, "load_field_map"),
)


@dataclass(frozen=True)
class CacheSite:
    file: str
    line: int
    name: str

    def as_dict(self) -> dict[str, Any]:
        return {"file": self.file, "line": self.line, "name": self.name}

    def label(self) -> str:
        return f"{self.file}:{self.line} {self.name}"


def known_sites() -> tuple[CacheSite, ...]:
    return tuple(CacheSite(path, line, name) for path, line, name in KNOWN_CACHES)


def _decorator_is_cache(dec: ast.expr) -> bool:
    text = ast.unparse(dec).replace(" ", "")
    if text in {"cache", "functools.cache"} or text.endswith(".cache"):
        return True
    return ".lru_cache" in text or text.startswith(("lru_cache", "cache(", "functools.cache"))


def discover_cache_sites(root: Path | None = None) -> list[CacheSite]:
    """AST-scan product packages for module-level caches."""
    root = root or REPO_ROOT
    found: list[CacheSite] = []
    for folder in _SCAN_ROOTS:
        base = root / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if any(part in path.parts for part in (".venv", "site-packages", "__pycache__")):
                continue
            rel = path.relative_to(root).as_posix()
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for dec in node.decorator_list:
                        if _decorator_is_cache(dec):
                            found.append(CacheSite(rel, dec.lineno, node.name))
                            break
                elif isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and (
                            "cache" in target.id.lower() or target.id == "_engine"
                        ):
                            found.append(CacheSite(rel, node.lineno, target.id))
                elif (
                    isinstance(node, ast.AnnAssign)
                    and isinstance(node.target, ast.Name)
                    and ("cache" in node.target.id.lower() or node.target.id == "_engine")
                ):
                    found.append(CacheSite(rel, node.lineno, node.target.id))
    found.sort(key=lambda site: (site.file, site.line, site.name))
    return found


def _site_key(site: CacheSite) -> tuple[str, int, str]:
    return (site.file, site.line, site.name)


def runtime_cached_callables() -> list[str]:
    """Import payloq packages and list callables that expose cache_clear."""
    import payloq_api
    import payloq_benchmark
    import payloq_cli
    import payloq_export_xlsx
    import payloq_generator
    import payloq_llm
    import payloq_schemas
    import payloq_validate

    names: list[str] = []
    for package in (
        payloq_schemas,
        payloq_generator,
        payloq_validate,
        payloq_llm,
        payloq_export_xlsx,
        payloq_benchmark,
        payloq_cli,
        payloq_api,
    ):
        prefix = package.__name__ + "."
        modules = [package]
        if hasattr(package, "__path__"):
            for info in pkgutil.walk_packages(package.__path__, prefix):
                try:
                    modules.append(importlib.import_module(info.name))
                except Exception:  # noqa: BLE001 — discovery must not hide a cache
                    names.append(f"{info.name}.<import failed>")
        for module in modules:
            for attr, obj in vars(module).items():
                if attr.startswith("__"):
                    continue
                if callable(obj) and hasattr(obj, "cache_clear"):
                    names.append(f"{module.__name__}.{attr}")
    return sorted(set(names))


def assert_registry_complete() -> None:
    """Raise if product code gained a module-level cache the harness does not clear."""
    discovered = discover_cache_sites()
    expected = sorted(known_sites(), key=_site_key)
    discovered = sorted(discovered, key=_site_key)
    if discovered != expected:
        got = "\n".join(site.label() for site in discovered) or "(none)"
        want = "\n".join(site.label() for site in expected) or "(none)"
        raise AssertionError(
            "module-level cache registry does not match the source scan\n"
            f"discovered:\n{got}\nregistry:\n{want}"
        )
    runtime = runtime_cached_callables()
    known_names = {site.name for site in expected}
    unexpected = [name for name in runtime if name.rsplit(".", 1)[-1] not in known_names]
    if unexpected:
        raise AssertionError(
            "new runtime lru_cache callable(s) not in the harness registry: "
            + ", ".join(unexpected)
        )


_REGISTRY_OK = False


def clear_module_caches() -> list[CacheSite]:
    """Clear every registered cache. Fails closed when a new cache appears."""
    global _REGISTRY_OK
    if not _REGISTRY_OK:
        assert_registry_complete()
        _REGISTRY_OK = True
    from payloq_api import config as api_config
    from payloq_api import db as api_db
    from payloq_schemas.field_map import load_field_map

    load_field_map.cache_clear()
    api_config.get_settings.cache_clear()
    api_db._engine = None
    return list(known_sites())


def cache_labels() -> list[str]:
    return [site.label() for site in known_sites()]
