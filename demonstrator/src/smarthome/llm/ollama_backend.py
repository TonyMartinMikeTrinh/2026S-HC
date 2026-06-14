"""On-device LLM backend via Ollama (default model ``llama3.1:latest``).

``llama3.1`` is one of the compact on-device models named in the research report
(§3.2) and supports native tool-calling, which we use to turn natural language
into structured device actions.

Some models/versions occasionally emit the function call as JSON *content* instead
of via the native ``tool_calls`` field, so we parse both: native tool calls first,
then a tolerant fallback that extracts tool-call objects from the reply text.
"""
from __future__ import annotations

import ast
import json

from ..core import config
from .base import ALLOWED_TOOLS, SYSTEM_PROMPT, TOOLS, Decision, LLMBackend, ToolCall


def _loads_tolerant(text: str):
    """Parse JSON, tolerating model quirks (Python ``True``/``False``, quotes)."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        try:
            return ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return None


def _json_objects(text: str) -> list[str]:
    """Return the top-level ``{...}`` substrings in ``text`` (brace matching)."""
    objs: list[str] = []
    depth, start = 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                objs.append(text[start:i + 1])
                start = None
    return objs


def _toolcall_from_obj(obj: dict) -> ToolCall | None:
    fn = obj.get("function") if isinstance(obj.get("function"), dict) else {}
    name = obj.get("name") or obj.get("tool") or fn.get("name")
    args = obj.get("parameters")
    if args is None:
        args = obj.get("arguments")
    if args is None:
        args = fn.get("arguments")
    if isinstance(args, str):
        args = _loads_tolerant(args)
    if name in ALLOWED_TOOLS and isinstance(args, dict):
        return ToolCall(name=name, arguments=dict(args))
    return None


def _toolcalls_from_content(content: str) -> list[ToolCall]:
    """Best-effort: recover tool calls a model wrote into its text content."""
    calls: list[ToolCall] = []
    for blob in _json_objects(content):
        obj = _loads_tolerant(blob)
        if isinstance(obj, dict):
            call = _toolcall_from_obj(obj)
            if call is not None:
                calls.append(call)
    return calls


class OllamaBackend(LLMBackend):
    name = "ollama"

    def __init__(self, model: str | None = None, host: str | None = None) -> None:
        import ollama  # imported lazily so the package imports without ollama running
        self.model = model or config.OLLAMA_MODEL
        self._client = ollama.Client(host=host or config.OLLAMA_HOST, timeout=120)

    def available(self) -> bool:
        """True if the Ollama server is reachable (model pull is the user's job)."""
        try:
            self._client.list()
            return True
        except Exception:  # noqa: BLE001 — server down / not installed
            return False

    def decide(self, text: str, world_summary: str) -> Decision:
        messages = [
            {"role": "system",
             "content": f"{SYSTEM_PROMPT}\n\nCurrent home state:\n{world_summary}"},
            {"role": "user", "content": text},
        ]
        resp = self._client.chat(model=self.model, messages=messages, tools=TOOLS,
                                 options={"temperature": 0})
        msg = resp["message"]

        calls: list[ToolCall] = []
        for tc in (msg.get("tool_calls") or []):
            fn = tc["function"]
            args = fn.get("arguments", {})
            if isinstance(args, str):
                args = _loads_tolerant(args) or {}
            calls.append(ToolCall(name=fn["name"], arguments=dict(args)))

        content = (msg.get("content") or "").strip()
        if not calls and content:
            # Fallback: the model put the call in the text instead of tool_calls.
            recovered = _toolcalls_from_content(content)
            if recovered:
                calls = recovered
                content = ""        # the content was the call, not a user-facing reply
        return Decision(tool_calls=calls, reply=content)
