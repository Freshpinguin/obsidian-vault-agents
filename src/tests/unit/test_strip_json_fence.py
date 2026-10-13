import pytest
from src.agentic.engine.response import strip_json_fence


def test_strip_json_fence_without_fence():
    raw = '{"reply": "normal json"}'
    assert strip_json_fence(raw) == raw


def test_strip_json_fence_with_json_fence():
    raw = '```json\n{"reply": "inside json fence"}\n```'
    assert strip_json_fence(raw) == '{"reply": "inside json fence"}'


def test_strip_json_fence_with_plain_fence():
    raw = '```\n{"reply": "inside plain fence"}\n```'
    assert strip_json_fence(raw) == '{"reply": "inside plain fence"}'


def test_strip_json_fence_only_opening_fence():
    raw = '```json\n{"reply": "no closing fence"}'
    assert strip_json_fence(raw) == '{"reply": "no closing fence"}'


def test_strip_json_fence_empty_string():
    assert strip_json_fence("") == ""
    assert strip_json_fence("   ") == ""
