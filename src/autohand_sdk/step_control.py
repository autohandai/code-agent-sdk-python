"""Host-side predicates for stopping after completed, persisted tool steps."""

from autohand_sdk.types import StopCondition, StopConditionContext


def is_step_count(count: int) -> StopCondition:
    """Stop when at least ``count`` tool steps have completed in this run."""
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("is_step_count requires a positive integer")

    def condition(context: StopConditionContext) -> bool:
        return len(context.steps) >= count

    return condition


def has_tool_call(tool_name: str) -> StopCondition:
    """Stop after a completed step that called the named tool."""
    name = tool_name.strip()
    if not name:
        raise ValueError("has_tool_call requires a non-empty tool name")

    def condition(context: StopConditionContext) -> bool:
        return bool(context.steps) and any(
            call.tool == name for call in context.steps[-1].tool_calls
        )

    return condition
