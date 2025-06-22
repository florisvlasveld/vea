# ruff: noqa: E402
import logging
import types
import sys
import importlib

import pytest


def _setup_openai(monkeypatch):
    class DummyChat:
        def __init__(self):
            self.completions = types.SimpleNamespace(create=self.create)

        def create(self, **kwargs):
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="ok"))],
                usage=types.SimpleNamespace(total_tokens=11),
            )

    class DummyOpenAI:
        def __init__(self):
            self.chat = DummyChat()
            self.responses = types.SimpleNamespace(create=lambda **kw: None)

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=DummyOpenAI))


def _setup_anthropic(monkeypatch):
    class DummyMessages:
        @staticmethod
        def create(**kwargs):
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(text="ok")],
                usage=types.SimpleNamespace(input_tokens=5, output_tokens=6),
            )

    class DummyAnthropic:
        def __init__(self):
            self.messages = DummyMessages()

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=DummyAnthropic))


def _setup_genai(monkeypatch):
    class DummyChat:
        def send_message(self, *a, **k):
            return types.SimpleNamespace(text="ok", usage_metadata=types.SimpleNamespace(total_tokens=7))

    class DummyModel:
        def __init__(self, name):
            self.name = name

        def start_chat(self, history=None):
            return DummyChat()

    genai_mod = types.ModuleType("google.generativeai")
    genai_mod.GenerativeModel = DummyModel
    genai_mod.configure = lambda *a, **k: None
    monkeypatch.setitem(sys.modules, "google.generativeai", genai_mod)
    monkeypatch.setitem(sys.modules, "google", types.SimpleNamespace(generativeai=genai_mod))


def _reload_llm():
    import vea.utils.llm_utils as llm
    return importlib.reload(llm)


def test_openai_logging(monkeypatch, caplog):
    _setup_openai(monkeypatch)
    _setup_anthropic(monkeypatch)
    _setup_genai(monkeypatch)
    llm = _reload_llm()
    with caplog.at_level(logging.DEBUG):
        result = llm.run_llm_prompt("hi there", model="gpt-4", quiet=True)
    assert result == "ok"
    joined = "\n".join(r.message for r in caplog.records)
    assert "Prompt length" in joined
    assert "total_tokens=11" in joined


def test_anthropic_logging(monkeypatch, caplog):
    _setup_openai(monkeypatch)
    _setup_anthropic(monkeypatch)
    _setup_genai(monkeypatch)
    llm = _reload_llm()
    with caplog.at_level(logging.DEBUG):
        result = llm.run_llm_prompt("hello", model="claude-3-haiku", quiet=True)
    assert result == "ok"
    joined = "\n".join(r.message for r in caplog.records)
    assert "Prompt length" in joined
    assert "input_tokens=5" in joined and "output_tokens=6" in joined


def test_gemini_logging(monkeypatch, caplog):
    _setup_openai(monkeypatch)
    _setup_anthropic(monkeypatch)
    _setup_genai(monkeypatch)
    llm = _reload_llm()
    with caplog.at_level(logging.DEBUG):
        result = llm.run_llm_prompt("yo", model="gemini-1.5-pro", quiet=True)
    assert result == "ok"
    joined = "\n".join(r.message for r in caplog.records)
    assert "Prompt length" in joined
    assert "total_tokens=7" in joined
