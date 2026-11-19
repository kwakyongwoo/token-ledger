"""Read Claude Code transcripts (~/.claude/projects/*/*.jsonl) into per-prompt usage.

The format is undocumented: unknown line types and fields are skipped, never fatal.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .pricing import request_cost

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def projects_dir() -> Path:
    return Path(os.environ.get("TOKEN_LEDGER_PROJECTS", Path.home() / ".claude" / "projects"))


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def is_prompt(d: dict) -> bool:
    """A message the person typed: not tool results, injected context, notifications or interrupts."""
    if d.get("type") != "user" or d.get("isMeta") or d.get("isSidechain"):
        return False
    content = (d.get("message") or {}).get("content")
    if d.get("toolUseResult") is not None:
        return False
    if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return False
    origin = d.get("origin")
    if isinstance(origin, dict):  # newer transcripts say who wrote the line
        return origin.get("kind") == "human" and d.get("turnPosition") is not None
    text = _text(content).lstrip()  # older transcripts: fall back to known non-prompt prefixes
    return bool(text) and not text.startswith(("[Request interrupted", "<task-notification>", "<local-command", "<bash-"))


def excerpt(d: dict) -> str:
    text = " ".join(_text((d.get("message") or {}).get("content")).split())
    if text.startswith("<command-message>"):
        text = text.split("</command-message>")[0].replace("<command-message>", "/")
    return text[:80]


@dataclass
class Usage:
    requests: int = 0
    input: int = 0
    output: int = 0
    cache_write: int = 0
    cache_read: int = 0
    thinking: int = 0  # part of output, kept for display only
    cost: float | None = 0.0

    def add(self, model: str | None, u: dict) -> None:
        self.requests += 1
        self.input += u.get("input_tokens") or 0
        self.output += u.get("output_tokens") or 0
        self.cache_write += u.get("cache_creation_input_tokens") or 0
        self.cache_read += u.get("cache_read_input_tokens") or 0
        self.thinking += (u.get("output_tokens_details") or {}).get("thinking_tokens") or 0
        c = request_cost(model, u)
        self.cost = None if c is None or self.cost is None else self.cost + c


@dataclass
class Prompt:
    id: str
    session: str
    ts: str
    excerpt: str
    end_ts: str = ""
    cwd: str | None = None
    branch: str | None = None
    models: dict = field(default_factory=dict)  # model -> Usage
    tools: int = 0
    tool_use_ids: list = field(default_factory=list)
    files: set = field(default_factory=set)  # absolute paths
    subagents: int = 0
    seen_requests: set = field(default_factory=set)

    def add_assistant(self, d: dict, in_repo) -> None:
        msg = d.get("message") or {}
        for b in msg.get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                self.tools += 1
                self.tool_use_ids.append(b.get("id"))
                inp = b.get("input") or {}
                path = inp.get("file_path") or inp.get("notebook_path")
                if b.get("name") in EDIT_TOOLS and isinstance(path, str):
                    self.files.add(path)
        if not in_repo(d.get("cwd")):
            return
        rid = d.get("requestId") or msg.get("id")
        if rid in self.seen_requests:  # one API response is written as one line per content block
            return
        self.seen_requests.add(rid)
        usage = msg.get("usage")
        model = msg.get("model")
        if not usage or model == "<synthetic>":
            return
        if self.cwd is None:
            self.cwd, self.branch = d.get("cwd"), d.get("gitBranch")
        self.models.setdefault(model, Usage()).add(model, usage)
        self.end_ts = d.get("timestamp") or self.end_ts


def _lines(path: Path, offset: int):
    """Yield (start, end, parsed_line) from offset; stops before a trailing partial line."""
    with open(path, "rb") as f:
        f.seek(offset)
        pos = offset
        for raw in f:
            if not raw.endswith(b"\n"):
                return
            start, pos = pos, pos + len(raw)
            try:
                yield start, pos, json.loads(raw)
            except ValueError:
                continue


def read_session(path: Path, offset: int, in_repo, closed_at_eof: bool):
    """Prompts from offset on. Returns (closed_prompts, title, next_offset).

    next_offset points at the first prompt still open, so it is read again next time.
    """
    prompts: list[tuple[int, Prompt]] = []
    title = None
    end = offset
    for start, end, d in _lines(path, offset):
        t = d.get("type")
        if t == "custom-title":
            title = d.get("customTitle") or title
        elif is_prompt(d):
            pid = d.get("promptId") or d.get("uuid")
            prompts.append((start, Prompt(pid, d.get("sessionId", path.stem), d.get("timestamp", ""), excerpt(d))))
        elif t == "assistant" and prompts and not d.get("isSidechain"):
            prompts[-1][1].add_assistant(d, in_repo)
    next_offset = end  # just past the last complete line
    if prompts and not closed_at_eof:
        next_offset = prompts[-1][0]
        prompts = prompts[:-1]
    for _, p in prompts:
        add_subagents(path, p, in_repo)
    return [p for _, p in prompts], title, next_offset


def add_subagents(session_path: Path, p: Prompt, in_repo) -> None:
    """Fold subagent transcripts launched from this prompt into it (recursively)."""
    sub_dir = session_path.parent / session_path.stem / "subagents"
    if not sub_dir.is_dir():
        return
    by_tool = {}
    for meta in sub_dir.glob("*.meta.json"):
        try:
            by_tool[json.loads(meta.read_text()).get("toolUseId")] = meta
        except (ValueError, OSError):
            continue
    queue = list(p.tool_use_ids)
    while queue:
        meta = by_tool.pop(queue.pop(), None)
        if meta is None:
            continue
        jsonl = meta.with_name(meta.name[: -len(".meta.json")] + ".jsonl")
        if not jsonl.exists():
            continue
        p.subagents += 1
        before = len(p.tool_use_ids)
        for _, _, d in _lines(jsonl, 0):
            if d.get("type") == "assistant":
                d = dict(d, isSidechain=False)
                p.add_assistant(d, in_repo)
        queue.extend(p.tool_use_ids[before:])
