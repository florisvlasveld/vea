# ruff: noqa: E402
import sys
import types
from types import SimpleNamespace

# Create minimal stubs so llm_utils can be imported without real dependencies
sys.modules.setdefault("anthropic", SimpleNamespace())
sys.modules.setdefault("openai", SimpleNamespace())
_google_pkg = types.ModuleType("google")
_genai = types.ModuleType("generativeai")
_genai.configure = lambda *a, **k: None
_google_pkg.generativeai = _genai
sys.modules.setdefault("google", _google_pkg)
sys.modules.setdefault("google.generativeai", _genai)

from vea.utils import llm_utils


def _setup_openai_stub(monkeypatch, log):
    class DummyChatCompletions:
        def create(self, **kwargs):
            log.append(("chat", kwargs))
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="chat"))])

    class DummyCompletions:
        def create(self, **kwargs):
            log.append(("completion", kwargs))
            return SimpleNamespace(choices=[SimpleNamespace(text="completion")])

    class DummyClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=DummyChatCompletions())
            self.completions = DummyCompletions()

    openai_stub = SimpleNamespace(api_key=None, OpenAI=lambda: DummyClient())
    monkeypatch.setattr(llm_utils, "openai", openai_stub, raising=False)


def test_chat_model_uses_chat_endpoint(monkeypatch):
    log = []
    _setup_openai_stub(monkeypatch, log)
    result = llm_utils.run_llm_prompt("hi", model="gpt-4", quiet=True)
    assert result == "chat"
    assert log and log[0][0] == "chat"
    assert "messages" in log[0][1]


def test_completion_model_uses_completion_endpoint(monkeypatch):
    log = []
    _setup_openai_stub(monkeypatch, log)
    result = llm_utils.run_llm_prompt("hi", model="o3-pro-2025-06-10", quiet=True)
    assert result == "completion"
    assert log and log[0][0] == "completion"
    assert "prompt" in log[0][1]


def test_is_completion_model():
    assert llm_utils.is_completion_model("o3-pro-2025-06-10")
    assert llm_utils.is_completion_model("text-davinci-003")
    assert not llm_utils.is_completion_model("gpt-4")
