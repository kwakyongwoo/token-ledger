"""Shared work-unit names (vocabulary.jsonl) and prompt assignments (units/<member>/*.jsonl).

vocabulary.jsonl has one name per line, sorted, so edits to different names merge cleanly.
Assignments are write-once chunk files like the data rows: a prompt keeps its first unit forever,
and merges/renames are resolved through aliases at read time.
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path


def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]


class Vocabulary:
    def __init__(self, out_dir: Path):
        self.path = out_dir / "vocabulary.jsonl"
        self.entries: dict[str, dict] = {}
        try:
            lines = self.path.read_text().splitlines()
        except OSError:
            lines = []
        for line in lines:  # a conflict marker or broken line skips only itself
            try:
                e = json.loads(line)
                self.entries[e["name"]] = e
            except (ValueError, KeyError, TypeError):
                continue

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("".join(json.dumps(self.entries[n], ensure_ascii=False, sort_keys=True) + "\n"
                                     for n in sorted(self.entries)))

    def resolve(self, name: str | None) -> str | None:
        """Canonical name for a name or alias (follows merge chains)."""
        seen = set()
        while name and name not in self.entries and name not in seen:
            seen.add(name)
            owner = next((n for n, e in self.entries.items() if name in e.get("aliases", [])), None)
            if owner is None:
                return name
            name = owner
        return name

    def add(self, name: str, new: bool = True) -> str:
        name = self.resolve(normalize(name)) or name
        if name not in self.entries:
            self.entries[name] = {"name": name, "aliases": [], "new": new,
                                  "added": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
        return name

    def merge(self, src: str, dst: str) -> str:
        src, dst = normalize(src), normalize(dst)
        if src not in self.entries:
            owner = self.resolve(src)
            return f"unknown name: {src}" if owner == src else f"{src} is already an alias of {owner}"
        dst = self.resolve(dst)
        if dst == src:
            return f"{src} and {dst} are already the same unit"
        dst = self.add(dst, new=False)
        moved = self.entries.pop(src)
        self.entries[dst]["aliases"] = sorted((set(self.entries[dst]["aliases"]) | {src} | set(moved.get("aliases", []))) - {dst})
        return f"merged {src} into {dst}"

    def rename(self, old: str, new: str) -> str:
        old, new = normalize(old), normalize(new)
        if old not in self.entries:
            return f"unknown name: {old}"
        if new in self.entries or self.resolve(new) != new:
            return f"{new} already exists; use merge {old} {new}"
        e = self.entries.pop(old)
        e.update(name=new, aliases=sorted(set(e["aliases"]) | {old}), new=False)
        self.entries[new] = e
        return f"renamed {old} to {new}"

    def ok(self, names: list[str]) -> str:
        targets = [self.resolve(normalize(n)) for n in names] or list(self.entries)
        for n in targets:
            if n in self.entries:
                self.entries[n]["new"] = False
        return f"cleared NEW on {len(targets)} name(s)"

    def close(self, name: str) -> list[str]:
        """Existing names that share a word with name (to suggest before creating a new one)."""
        words = set(normalize(name).split("-")) - {""}
        return sorted(n for n, e in self.entries.items()
                      if words & set("-".join([n, *e.get("aliases", [])]).split("-")))[:5]


def read_assignments(out_dir: Path) -> dict[str, str]:
    """{prompt id: unit} from every chunk; the first assignment (by file name) wins."""
    ids: dict[str, str] = {}
    for f in sorted((out_dir / "units").glob("*/*.jsonl"), key=lambda f: (f.name, str(f))):  # time-stamped names
        for line in f.read_text().splitlines():
            try:
                r = json.loads(line)
                ids.setdefault(r["id"], r["unit"])
            except (ValueError, KeyError):
                continue
    return ids


def write_assignments(out_dir: Path, member_slug: str, pairs: dict[str, str]) -> Path | None:
    if not pairs:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / "units" / member_slug / f"{stamp}-{secrets.token_hex(3)}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps({"id": i, "unit": u}) + "\n" for i, u in sorted(pairs.items())))
    return path
