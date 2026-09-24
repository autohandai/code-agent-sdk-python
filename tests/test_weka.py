from __future__ import annotations

import json

import httpx
import pytest

from autohand_sdk import (
    WekaChoiceAnswer,
    WekaChoiceQuestion,
    WekaClient,
    WekaDecisionRequest,
    WekaNoulAnswer,
    WekaNoulCriteria,
    WekaNoulQuestion,
    WekaRequestError,
    WekaScoreAnswer,
    WekaScoreQuestion,
    WekaValidationError,
)


def decision_request() -> WekaDecisionRequest:
    """Build a representative choice and score request."""
    return WekaDecisionRequest(
        state={"tests": "passed", "changed_systems": ["checkout"]},
        questions={
            "needs_review": WekaNoulQuestion(
                instructions="Does this release need a person?",
                criteria=WekaNoulCriteria(
                    true="A person must review the evidence.",
                    false="The automated checks are sufficient.",
                ),
            ),
            "release_lane": WekaChoiceQuestion(
                instructions="Choose the safest release lane.",
                criteria={
                    "continue": "All required checks passed.",
                    "review": "The evidence needs a person.",
                },
            ),
            "risk": WekaScoreQuestion(
                instructions="Score the release risk.",
                criteria=["Low risk", "Medium risk", "High risk"],
            ),
        },
    )


@pytest.mark.asyncio
async def test_decide_sends_contract_and_returns_typed_answers() -> None:
    """The client sends auth and returns discriminated answer models."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"x-request-id": "req-success"},
            json={
                "model": "weka",
                "answers": {
                    "needs_review": {"type": "noul", "noul": 0.73},
                    "release_lane": {
                        "type": "choice",
                        "choice": "review",
                        "confidence": 0.82,
                        "probabilities": {"continue": 0.18, "review": 0.82},
                    },
                    "risk": {
                        "type": "score",
                        "score": 1.3,
                        "confidence": 0.7,
                        "legend": {"0": "Low risk", "1": "Medium risk", "2": "High risk"},
                        "probabilities": {"0": 0.1, "1": 0.5, "2": 0.4},
                    },
                },
                "usage": {"input_tokens": 426, "output_tokens": 73},
            },
        )

    async with WekaClient(
        api_key="test-key",
        base_url="https://example.test/",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.decide(decision_request())

    assert isinstance(result.answers["release_lane"], WekaChoiceAnswer)
    assert isinstance(result.answers["needs_review"], WekaNoulAnswer)
    assert result.answers["needs_review"].noul == 0.73
    assert result.answers["release_lane"].choice == "review"
    assert isinstance(result.answers["risk"], WekaScoreAnswer)
    assert result.answers["risk"].score == 1.3
    assert result.usage.input_tokens == 426
    assert captured == {
        "url": "https://example.test/v1/decisions",
        "authorization": "Bearer test-key",
        "body": decision_request().model_dump(mode="json"),
    }


@pytest.mark.asyncio
async def test_decide_rejects_invalid_request_before_transport() -> None:
    """Malformed score criteria fail before a network request."""
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    async with WekaClient(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(WekaValidationError):
            await client.decide(
                {
                    "model": "weka",
                    "state": {},
                    "questions": {
                        "risk": {
                            "type": "score",
                            "instructions": "Score the risk.",
                            "criteria": ["Only one anchor"],
                        }
                    },
                }
            )

    assert calls == 0


@pytest.mark.asyncio
async def test_decide_rejects_unrequested_choice() -> None:
    """A choice outside the request criteria is rejected."""
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "weka",
                "answers": {
                    "needs_review": {"type": "noul", "noul": 0.73},
                    "release_lane": {
                        "type": "choice",
                        "choice": "blocked",
                        "confidence": 0.99,
                        "probabilities": {"continue": 0.01, "review": 0, "blocked": 0.99},
                    },
                    "risk": {
                        "type": "score",
                        "score": 0,
                        "confidence": 1,
                        "legend": {"0": "Low risk", "1": "Medium risk", "2": "High risk"},
                        "probabilities": {"0": 1, "1": 0, "2": 0},
                    },
                },
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )

    async with WekaClient(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(WekaRequestError, match="unexpected response shape"):
            await client.decide(decision_request())


@pytest.mark.asyncio
async def test_decide_reports_status_without_exposing_response_body() -> None:
    """HTTP errors retain metadata without echoing an arbitrary body."""
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"x-request-id": "req-rate-limit"},
            json={"secret": "must-not-appear"},
        )

    async with WekaClient(
        api_key="test-key",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(WekaRequestError) as captured:
            await client.decide(decision_request())

    assert captured.value.status == 429
    assert captured.value.request_id == "req-rate-limit"
    assert "must-not-appear" not in str(captured.value)
