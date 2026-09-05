"""High-level structured output matches the TypeScript run contract."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel, ValidationError

from autohand_sdk import Agent, AutohandSDK, PromptParams, Run, RunResult, StructuredOutputError


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"answer":1}', {"answer": 1}),
        ('Here it is:\n```json\n{"answer":1}\n```\nDone.', {"answer": 1}),
        ('Result: {"answer":["}\\"[",2]} done.', {"answer": ['}"[', 2]}),
        ('[invalid] and {"answer":1}', {"answer": 1}),
        ("null", None),
        ("false", False),
    ],
)
async def test_parse_json_responses(text: str, expected: object) -> None:
    """Accept direct JSON, fenced JSON, and embedded balanced JSON values."""
    run = Run(AutohandSDK(), PromptParams(message="unused"))
    with patch.object(
        run,
        "wait",
        AsyncMock(
            return_value=RunResult(
                id="fixture",
                status="completed",
                text=text,
                events=[],
                steps=[],
            )
        ),
    ):
        assert await run.json() == expected


@pytest.mark.parametrize("text", ["", "not JSON", "{broken]", "NaN"])
async def test_invalid_json_keeps_response(text: str) -> None:
    """Report structured output failure with its original response for diagnosis."""
    run = Run(AutohandSDK(), PromptParams(message="unused"))
    with (
        patch.object(
            run,
            "wait",
            AsyncMock(
                return_value=RunResult(
                    id="fixture",
                    status="completed",
                    text=text,
                    events=[],
                    steps=[],
                )
            ),
        ),
        pytest.raises(StructuredOutputError) as error,
    ):
        await run.json()
    assert error.value.raw_response == text


async def test_schema_instruction_and_validation() -> None:
    """Keep output instructions on the prompt and return a validated Pydantic result."""

    class Summary(BaseModel):
        answer: int

    sdk = AutohandSDK()
    seen = []

    async def stream(params: PromptParams):
        seen.append(params)
        yield {"type": "message_end", "content": '{"answer":1}'}
        yield {"type": "agent_end", "reason": "completed"}

    with patch.object(sdk, "_stream_prompt", stream):
        result = await Agent.from_sdk(sdk).json(
            "Inspect",
            schema=Summary.model_json_schema(),
            schema_name="Summary",
            output_instructions="Use integer answers.",
            validate=Summary.model_validate,
        )
        assert isinstance(result, Summary) and result.answer == 1
        assert "Summary" in seen[0].message
        assert "Use integer answers." in seen[0].message
        assert json.dumps(Summary.model_json_schema()) in seen[0].message
        assert set(seen[0].model_dump(exclude_none=True)) == {"message"}
        with pytest.raises(ValidationError):
            await Agent.from_sdk(sdk).json("Inspect", validate=lambda _: Summary(answer="invalid"))
