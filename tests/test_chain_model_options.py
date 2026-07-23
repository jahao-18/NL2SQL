from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from app.core import chain


def test_qwen3_call_disables_thinking_by_default(monkeypatch):
    captured = {}

    def fake_call(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            status_code=200,
            output=SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=[{"text": "SELECT 1"}])
                    )
                ]
            ),
        )

    import dashscope

    monkeypatch.setattr(dashscope.MultiModalConversation, "call", fake_call)
    monkeypatch.setattr(chain.settings, "llm_enable_thinking", False)
    model = chain.ChatQwenMultiModal(
        model="qwen3.6-plus",
        dashscope_api_key="test-key",
        temperature=0,
    )

    result = model._generate([HumanMessage(content="generate SQL")])

    assert result.generations[0].message.content == "SELECT 1"
    assert captured["enable_thinking"] is False
    assert captured["timeout"] == chain.settings.llm_timeout_seconds
