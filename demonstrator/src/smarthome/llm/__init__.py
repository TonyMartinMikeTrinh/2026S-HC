"""On-device LLM backends for the orchestration agent.

A small abstraction (``LLMBackend``) with two implementations:

* :class:`OllamaBackend` — a local LLM (default ``llama3.1:latest``) using native
  tool-calling, embodying the research's "on-device inference runtime" (A-19).
* :class:`RuleBackend` — a deterministic keyword intent parser, so the demo runs
  fully offline even when no model is loaded (graceful degradation).
"""
