"""JSONL logging wrapper for smolagents Tool instances.

Tools in this baseline run in a deterministic pipeline instead of through an
agent's native tool-calling loop (see README.md), so there is no built-in
transcript of which tool was called when. This module makes that transcript
explicit: every tool call is written as one JSON object per line (JSON Lines
/ NDJSON), independent of whether the tool is case-scoped
(list_case_documents, read_pdf, search_case), global (lookup_policy,
check_facts), or corpus-scoped (retrieve_<corpus>). By default lines go to
stdout; `predict.py` redirects them to `tool-calls.log` next to
`predictions.jsonl` via `log_to_file()`.

See README.md "Tool-call logging" for the documented line contract.
"""

import contextlib
import contextvars
import functools
import inspect
import json
import sys
from datetime import datetime, timezone
from typing import Any, IO, Iterator

from smolagents import Tool

_current_context: contextvars.ContextVar[str] = contextvars.ContextVar(
    "tool_call_context", default="-"
)

_current_destination: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "tool_call_destination", default=None
)

# Arguments and results are previewed (not dumped in full) to keep log lines
# short and greppable even when a tool reads a multi-page PDF or a policy
# dictionary; see _preview()'s docstring for the exact truncation rule.
PREVIEW_LIMIT = 200


@contextlib.contextmanager
def case_context(context: str) -> Iterator[None]:
    """Tag every tool call logged while this context manager is active.

    Usage: `with case_context("dienstreiseantrag-01"): ...` around the code
    that processes one case, regardless of how many tools it calls.
    """
    token = _current_context.set(context)
    try:
        yield
    finally:
        _current_context.reset(token)


@contextlib.contextmanager
def log_to_file(path: Any) -> Iterator[None]:
    """Write every tool-call log line to `path` instead of stdout.

    Usage: `with log_to_file(output_dir / "tool-calls.log"): ...` around the
    code whose tool calls should be captured; the file is opened once
    (truncating any previous contents) and closed on exit.
    """
    with open(path, "w", encoding="utf-8") as destination:
        token = _current_destination.set(destination)
        try:
            yield
        finally:
            _current_destination.reset(token)


def _write(entry: dict[str, Any]) -> None:
    destination: IO[str] = _current_destination.get() or sys.stdout
    print(json.dumps(entry, ensure_ascii=False), file=destination, flush=True)


def _preview(value: Any, limit: int = PREVIEW_LIMIT) -> Any:
    """Return value unchanged if it is a short JSON value, else a truncated preview string.

    Strings are whitespace-normalised and cut to `limit` characters. Other
    JSON-serialisable values (numbers, booleans, null, lists, dicts) are kept
    as-is when their JSON encoding is at most `limit` characters, so small
    structured arguments (e.g. check_facts' facts object) stay queryable as
    native JSON; larger ones fall back to a truncated string preview of their
    JSON encoding. Non-JSON-serialisable values fall back to str().
    """
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except TypeError:
            text = str(value)
        else:
            if len(text) <= limit:
                return value
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _bound_arguments(forward: Any, args: tuple, kwargs: dict) -> dict[str, Any]:
    """Map positional/keyword call arguments to parameter names by name."""
    try:
        bound = inspect.signature(forward).bind(*args, **kwargs)
        bound.apply_defaults()
        return dict(bound.arguments)
    except TypeError:
        # Fall back to positional indices if the signature does not match
        # (should not happen for the tools defined in this baseline).
        arguments = {f"arg{index}": value for index, value in enumerate(args)}
        arguments.update(kwargs)
        return arguments


def log_tool_calls(tool: Tool) -> Tool:
    """Wrap a Tool instance so every call is logged as one JSON line.

    Wraps forward() in place (not __call__) so smolagents' own argument
    validation still runs first; only successful and failed invocations of
    the underlying logic are logged. Lines go to stdout unless a
    `log_to_file()` context is active.
    """
    original_forward = tool.forward

    @functools.wraps(original_forward)
    def logged_forward(*args: Any, **kwargs: Any) -> Any:
        arguments = {
            name: _preview(value)
            for name, value in _bound_arguments(original_forward, args, kwargs).items()
        }
        entry: dict[str, Any] = {
            "case_id": _current_context.get(),
            "tool": tool.name,
            "arguments": arguments,
        }
        try:
            result = original_forward(*args, **kwargs)
        except Exception as error:
            entry["status"] = "error"
            entry["error"] = str(error)
            entry["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            _write(entry)
            raise

        entry["status"] = "ok"
        entry["error"] = None
        entry["timestamp"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        _write(entry)
        return result

    tool.forward = logged_forward
    return tool

