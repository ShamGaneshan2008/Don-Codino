import asyncio
from dataclasses import replace

import httpx

from app import prompt_engine


def test_template_is_honest_and_contains_acceptance(settings, workspace):
    (workspace / ".env").write_text("SECRET=private", encoding="utf-8")
    result = asyncio.run(prompt_engine.enhance("Build calculator", workspace, settings))
    assert result["mode"] == "template"
    assert "Build calculator" in result["prompt"]
    assert "README.md" in result["prompt"]
    assert "Acceptance:" in result["prompt"]
    assert "private" not in result["prompt"]
    assert ".env" not in result["prompt"]


def test_ai_refinement_uses_real_response_schema(settings, workspace, monkeypatch):
    original = httpx.AsyncClient

    def handle(request):
        assert request.url == "https://api.openai.com/v1/responses"
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "content": [
                            {"type": "output_text", "text": "Implement all four operations."},
                        ]
                    }
                ]
            },
        )

    monkeypatch.setattr(
        prompt_engine.httpx,
        "AsyncClient",
        lambda **kwargs: original(
            transport=httpx.MockTransport(handle),
            **kwargs,
        ),
    )
    result = asyncio.run(
        prompt_engine.enhance(
            "Build calculator",
            workspace,
            replace(settings, api_key="test-key", model="configured-model"),
        )
    )
    assert result["mode"] == "openai"
    assert result["prompt"].startswith("Implement all four operations.")
    assert "Do not push" in result["prompt"]
