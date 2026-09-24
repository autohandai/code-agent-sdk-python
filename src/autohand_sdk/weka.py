"""Typed client for Weka structured decisions."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from typing import Annotated, Any, Literal, TypeAlias

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, field_validator

from .errors import WekaRequestError, WekaValidationError

WekaDescription: TypeAlias = str | list[JsonValue] | dict[str, JsonValue] | None


class _WekaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class WekaNoulCriteria(_WekaModel):
    """Optional descriptions for the true and false outcomes of a noul."""

    true: WekaDescription = None
    false: WekaDescription = None


class WekaNoulQuestion(_WekaModel):
    """A calibrated yes-or-no probability question."""

    type: Literal["noul"] = "noul"
    instructions: WekaDescription
    criteria: WekaNoulCriteria | None = None


class WekaChoiceQuestion(_WekaModel):
    """A choice among named, application-defined outcomes."""

    type: Literal["choice"] = "choice"
    instructions: WekaDescription
    criteria: dict[str, WekaDescription] = Field(min_length=1)


class WekaScoreQuestion(_WekaModel):
    """A continuous score anchored by at least two ordered descriptions."""

    type: Literal["score"] = "score"
    instructions: WekaDescription
    criteria: list[WekaDescription] = Field(min_length=2)


WekaQuestion: TypeAlias = Annotated[
    WekaNoulQuestion | WekaChoiceQuestion | WekaScoreQuestion,
    Field(discriminator="type"),
]


class WekaDecisionRequest(_WekaModel):
    """Input accepted by the Weka decision endpoint."""

    model: Literal["weka"] = "weka"
    state: JsonValue
    questions: dict[str, WekaQuestion] = Field(min_length=1)

    @field_validator("state")
    @classmethod
    def state_is_finite_json(cls, value: JsonValue) -> JsonValue:
        """Reject non-finite numbers, which are not valid JSON."""
        if not _is_finite_json(value):
            raise ValueError("state must contain finite JSON values")
        return value

    @field_validator("questions")
    @classmethod
    def question_names_are_not_empty(
        cls, value: dict[str, WekaQuestion]
    ) -> dict[str, WekaQuestion]:
        """Require every answer key to have a corresponding non-empty name."""
        if any(not name for name in value):
            raise ValueError("question names must not be empty")
        return value


class WekaNoulAnswer(_WekaModel):
    """A calibrated probability for a noul question."""

    type: Literal["noul"]
    noul: float = Field(ge=0, le=1, allow_inf_nan=False)


class WekaChoiceAnswer(_WekaModel):
    """The selected choice with confidence and per-choice probabilities."""

    type: Literal["choice"]
    choice: str
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    probabilities: dict[str, float]

    @field_validator("probabilities")
    @classmethod
    def probabilities_are_bounded(cls, value: dict[str, float]) -> dict[str, float]:
        """Require every probability to be finite and within zero and one."""
        if not all(_is_probability(probability) for probability in value.values()):
            raise ValueError("probabilities must be between zero and one")
        return value


class WekaScoreAnswer(_WekaModel):
    """A continuous score with its calibrated discrete distribution."""

    type: Literal["score"]
    score: float = Field(allow_inf_nan=False)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    legend: dict[str, str]
    probabilities: dict[str, float]

    @field_validator("probabilities")
    @classmethod
    def probabilities_are_bounded(cls, value: dict[str, float]) -> dict[str, float]:
        """Require every probability to be finite and within zero and one."""
        if not all(_is_probability(probability) for probability in value.values()):
            raise ValueError("probabilities must be between zero and one")
        return value


WekaAnswer: TypeAlias = Annotated[
    WekaNoulAnswer | WekaChoiceAnswer | WekaScoreAnswer,
    Field(discriminator="type"),
]


class WekaUsage(_WekaModel):
    """Token usage reported for a Weka decision."""

    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class WekaDecisionResponse(_WekaModel):
    """Typed answers returned by Weka."""

    model: str = Field(min_length=1)
    answers: dict[str, WekaAnswer]
    usage: WekaUsage


class WekaClient:
    """Async client for ``POST /v1/decisions``."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        resolved_api_key = (
            api_key
            if api_key is not None
            else os.getenv("AUTOHAND_AI_API_KEY") or os.getenv("AUTOHAND_API_KEY")
        )
        if not resolved_api_key or not resolved_api_key.strip():
            raise WekaValidationError(
                "Set AUTOHAND_AI_API_KEY or pass api_key when creating WekaClient."
            )
        if not math.isfinite(timeout) or timeout <= 0:
            raise WekaValidationError("Weka timeout must be a positive finite number.")

        resolved_base_url = (
            base_url
            or os.getenv("AUTOHAND_AI_BASE_URL")
            or os.getenv("AUTOHAND_API_URL")
            or "https://api.autohand.ai"
        ).rstrip("/")
        try:
            parsed_base_url = httpx.URL(resolved_base_url)
        except (TypeError, ValueError) as error:
            raise WekaValidationError("Invalid Weka base URL.") from error
        if parsed_base_url.scheme not in {"http", "https"} or not parsed_base_url.host:
            raise WekaValidationError("Weka base URL must be an absolute HTTP or HTTPS URL.")

        self._client = httpx.AsyncClient(
            base_url=resolved_base_url,
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {resolved_api_key}",
                "content-type": "application/json",
            },
            timeout=timeout,
            transport=transport,
        )

    async def __aenter__(self) -> WekaClient:
        """Return this client for use in an async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        """Close the owned HTTP connection pool."""
        await self.close()

    async def close(self) -> None:
        """Close the owned HTTP connection pool."""
        await self._client.aclose()

    async def decide(
        self,
        request: WekaDecisionRequest | Mapping[str, Any],
    ) -> WekaDecisionResponse:
        """Evaluate structured state and return validated, typed Weka answers."""
        try:
            validated_request = (
                request
                if isinstance(request, WekaDecisionRequest)
                else WekaDecisionRequest.model_validate(request)
            )
        except ValidationError as error:
            raise WekaValidationError("Invalid Weka request.") from error

        try:
            response = await self._client.post(
                "/v1/decisions",
                json=validated_request.model_dump(mode="json"),
            )
        except httpx.HTTPError as error:
            raise WekaRequestError("Weka request could not be completed.") from error

        request_id = response.headers.get("x-request-id")
        if not response.is_success:
            suffix = f" ({request_id})" if request_id else ""
            raise WekaRequestError(
                f"Weka request failed with HTTP {response.status_code}{suffix}.",
                status=response.status_code,
                request_id=request_id,
            )

        try:
            result = WekaDecisionResponse.model_validate_json(response.content)
        except ValidationError as error:
            raise WekaRequestError(
                "Weka returned an unexpected response shape.",
                status=response.status_code,
                request_id=request_id,
            ) from error

        if not _answers_match_questions(result, validated_request):
            raise WekaRequestError(
                "Weka returned an unexpected response shape.",
                status=response.status_code,
                request_id=request_id,
            )
        return result


def _answers_match_questions(
    response: WekaDecisionResponse,
    request: WekaDecisionRequest,
) -> bool:
    if response.answers.keys() != request.questions.keys():
        return False
    for name, question in request.questions.items():
        answer = response.answers[name]
        if question.type != answer.type:
            return False
        if (
            isinstance(question, WekaChoiceQuestion)
            and isinstance(answer, WekaChoiceAnswer)
            and answer.choice not in question.criteria
        ):
            return False
    return True


def _is_probability(value: float) -> bool:
    return math.isfinite(value) and 0 <= value <= 1


def _is_finite_json(value: JsonValue) -> bool:
    if value is None or isinstance(value, (str, bool)):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_finite_json(item) for item in value)
    return all(isinstance(key, str) and _is_finite_json(item) for key, item in value.items())
