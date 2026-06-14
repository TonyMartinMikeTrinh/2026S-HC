"""Tolerant recovery of tool calls a model writes into its text content.

These are pure parser tests — no Ollama server required. They lock in the
fallback that makes models which emit the call as JSON *content* (instead of the
native ``tool_calls`` field, as llama3.1 sometimes does) still drive devices.
"""
from smarthome.llm.ollama_backend import (
    _json_objects,
    _loads_tolerant,
    _toolcalls_from_content,
)


def test_loads_tolerant_handles_python_literals():
    # Models sometimes emit Python-style True/False/None and single quotes.
    assert _loads_tolerant('{"on": true}') == {"on": True}
    assert _loads_tolerant("{'on': True, 'area': 'kitchen'}") == {"on": True, "area": "kitchen"}
    assert _loads_tolerant("not json") is None


def test_json_objects_extracts_top_level_braces():
    objs = _json_objects('prefix {"a": 1} middle {"b": {"c": 2}} end')
    assert objs == ['{"a": 1}', '{"b": {"c": 2}}']


def test_recovers_a_parameters_style_call():
    content = '{"name": "control_light", "parameters": {"area": "kitchen", "on": True}}'
    calls = _toolcalls_from_content(content)
    assert len(calls) == 1
    assert calls[0].name == "control_light"
    assert calls[0].arguments == {"area": "kitchen", "on": True}


def test_recovers_an_arguments_style_call():
    content = '{"name": "control_lock", "arguments": {"lock": true}}'
    calls = _toolcalls_from_content(content)
    assert calls and calls[0].name == "control_lock" and calls[0].arguments == {"lock": True}


def test_recovers_multiple_calls():
    content = ('Sure! {"name": "control_light", "parameters": {"on": false}} and '
               '{"name": "control_lock", "parameters": {"lock": true}}')
    names = [c.name for c in _toolcalls_from_content(content)]
    assert names == ["control_light", "control_lock"]


def test_ignores_unknown_tools_and_plain_text():
    assert _toolcalls_from_content("just a friendly sentence, no tools here") == []
    assert _toolcalls_from_content('{"name": "delete_everything", "parameters": {}}') == []
