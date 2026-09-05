"""JSON response extraction without quadratic retries on nested invalid input."""

import json
import re
from collections.abc import Iterator

from autohand_sdk.errors import StructuredOutputError


def _embedded_values(text: str) -> Iterator[str]:
    stack: list[str] = []
    start = 0
    in_string = escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"' and stack:
            in_string = True
        elif char in "[{":
            if not stack:
                start = index
            stack.append(char)
        elif stack and char in "]}":
            if (stack[-1], char) not in (("[", "]"), ("{", "}")):
                stack.clear()
                continue
            stack.pop()
            if not stack:
                yield text[start : index + 1]


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-JSON numeric constant: {value}")


def parse_json_text(text: str) -> object:
    """Parse direct JSON, then fenced values, then balanced embedded objects/arrays."""

    def candidates() -> Iterator[str]:
        yield text.strip()
        for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE):
            yield match[1]
        yield from _embedded_values(text)

    for candidate in candidates():
        try:
            return json.loads(candidate, parse_constant=_reject_constant)
        except ValueError:
            continue
    raise StructuredOutputError(text)
