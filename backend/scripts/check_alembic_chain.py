from __future__ import annotations

import ast
import sys
from pathlib import Path


def _read_assignment(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, ast.AnnAssign):
            if not isinstance(node.target, ast.Name):
                continue
            if node.target.id != name:
                continue
            if node.value is None:
                return None
            return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            if target.id != name:
                continue
            return ast.literal_eval(node.value)
    return None


def _normalize_down_revisions(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (tuple, list)):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            if not isinstance(item, str):
                raise ValueError(f"invalid down_revision item type: {type(item).__name__}")
            out.append(item)
        return out
    raise ValueError(f"invalid down_revision type: {type(value).__name__}")


def main() -> int:
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    if not versions_dir.is_dir():
        print(f"[ERROR] Alembic versions directory not found: {versions_dir}")
        return 1

    revisions: dict[str, Path] = {}
    down_map: dict[str, list[str]] = {}

    for path in sorted(versions_dir.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        revision = _read_assignment(tree, "revision")
        down_revision = _read_assignment(tree, "down_revision")

        if not isinstance(revision, str) or not revision.strip():
            print(f"[ERROR] {path.name}: invalid revision")
            return 1
        if revision in revisions:
            print(
                f"[ERROR] duplicate revision '{revision}' in {revisions[revision].name} and {path.name}"
            )
            return 1

        try:
            downs = _normalize_down_revisions(down_revision)
        except ValueError as exc:
            print(f"[ERROR] {path.name}: {exc}")
            return 1

        revisions[revision] = path
        down_map[revision] = downs

    missing: list[tuple[str, str]] = []
    referenced: set[str] = set()
    for rev, downs in down_map.items():
        for down in downs:
            referenced.add(down)
            if down not in revisions:
                missing.append((rev, down))

    if missing:
        for rev, down in missing:
            print(
                f"[ERROR] missing parent revision '{down}' referenced by '{rev}' ({revisions[rev].name})"
            )
        return 1

    heads = sorted(set(revisions) - referenced)
    roots = sorted(rev for rev, downs in down_map.items() if not downs)
    print(
        f"[OK] Alembic chain valid. revisions={len(revisions)} roots={len(roots)} heads={len(heads)}"
    )
    print(f"[OK] Heads: {', '.join(heads)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
