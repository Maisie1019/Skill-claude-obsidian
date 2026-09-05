#!/usr/bin/env python3
"""Validate a Markdown-based Obsidian vault without modifying it."""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml


REQUIRED = {"id", "type", "status", "created", "updated", "topics"}
TYPES = {"inbox", "source", "knowledge", "map", "system"}
STATUSES = {"inbox", "triaged", "draft", "review", "verified", "archived"}
EVIDENCE_TYPES = {"事实", "外部观点", "AI推断", "个人判断", "实测结果"}
WIKILINK = re.compile(r"!?(?:\[\[)([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
TEMPLATE_TOKEN = re.compile(r"\{\{[^}]+\}\}")


def frontmatter(text: str):
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return None
    parts = re.split(r"^---\s*$", text, maxsplit=2, flags=re.MULTILINE)
    if len(parts) < 3:
        return None
    try:
        return yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return None


def normalized_targets(root: Path, files: list[Path]) -> set[str]:
    targets: set[str] = set()
    for path in files:
        rel = path.relative_to(root).with_suffix("").as_posix()
        targets.add(rel.casefold())
        targets.add(path.stem.casefold())
    return targets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vault", type=Path)
    args = parser.parse_args()
    root = args.vault.resolve()
    if not root.is_dir():
        parser.error(f"not a directory: {root}")

    files = sorted(root.rglob("*.md"))
    targets = normalized_targets(root, files)
    ids: dict[str, list[Path]] = defaultdict(list)
    errors: list[str] = []
    warnings: list[str] = []

    for path in files:
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8-sig")
        is_template = "/Templates/" in f"/{rel}"
        meta = frontmatter(text)
        if meta is None:
            errors.append(f"{rel}: missing or invalid YAML frontmatter")
            continue
        if not isinstance(meta, dict):
            errors.append(f"{rel}: frontmatter must be a mapping")
            continue

        missing = REQUIRED - set(meta)
        if missing:
            errors.append(f"{rel}: missing fields: {', '.join(sorted(missing))}")
        note_id = str(meta.get("id", ""))
        if note_id and not TEMPLATE_TOKEN.search(note_id):
            ids[note_id].append(path)
        if meta.get("type") not in TYPES:
            errors.append(f"{rel}: invalid type {meta.get('type')!r}")
        if meta.get("status") not in STATUSES:
            errors.append(f"{rel}: invalid status {meta.get('status')!r}")
        if "topics" in meta and not isinstance(meta["topics"], list):
            errors.append(f"{rel}: topics must be a YAML list")
        if meta.get("type") == "knowledge":
            for field in ("sources", "evidence_types", "confidence", "reviewed_by"):
                if field not in meta:
                    errors.append(f"{rel}: knowledge note missing {field}")
            evidence_types = meta.get("evidence_types", [])
            if not isinstance(evidence_types, list):
                errors.append(f"{rel}: evidence_types must be a YAML list")
            elif invalid := set(evidence_types) - EVIDENCE_TYPES:
                errors.append(f"{rel}: invalid evidence_types: {', '.join(sorted(invalid))}")

        if not is_template:
            for target in WIKILINK.findall(text):
                clean = target.strip().replace("\\", "/").removesuffix(".md").casefold()
                if clean and clean not in targets:
                    warnings.append(f"{rel}: unresolved wikilink [[{target}]]")

    for note_id, paths in ids.items():
        if len(paths) > 1:
            joined = ", ".join(p.relative_to(root).as_posix() for p in paths)
            errors.append(f"duplicate id {note_id!r}: {joined}")

    for item in errors:
        print(f"ERROR: {item}")
    for item in warnings:
        print(f"WARN:  {item}")
    print(f"Checked {len(files)} Markdown files: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
