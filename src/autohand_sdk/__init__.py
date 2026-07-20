"""Autohand Agent SDK - Python implementation.

This SDK provides a Python wrapper around the Autohand CLI, enabling programmatic
control of AI agents through a high-level API. It supports streaming events,
permission management, model switching, and full lifecycle control of agent sessions.

Examples:
    Basic usage:

    >>> import asyncio
    >>> import os
    >>> from autohand_sdk import AutohandSDK
    >>>
    >>> async def main():
    ...     sdk = AutohandSDK(
    ...         cwd="/path/to/project",
    ...         provider="autohandai",
    ...         model="fantail",
    ...         api_key=os.environ["AUTOHAND_AI_API_KEY"],
    ...     )
    ...     await sdk.start()
    ...     async for event in sdk.stream_prompt(message="Hello"):
    ...         print(event)
    ...     await sdk.close()
    >>>
    >>> asyncio.run(main())

    With skills:

    >>> sdk = AutohandSDK(
    ...     cwd=".",
    ...     provider="autohandai",
    ...     model="fantail",
    ...     api_key=os.environ["AUTOHAND_AI_API_KEY"],
    ...     skill_refs=["typescript", "./skills/custom/SKILL.md"]
    ... )
"""

import importlib

__version__ = "0.1.0"
__all__ = [
    # Main classes
    "AutohandSDK",
    "Agent",
    "RPCClient",
    "Transport",
    "AutohandSDKError",
    "TransportError",
    "TransportNotStartedError",
    "RPCError",
    "RequestTimeoutError",
    # Config types
    "SDKConfig",
    "SDKEvent",
    "TypedSDKEvent",
    "AutomodeIterationEvent",
    "AutomodeCompleteEvent",
    "AutomodeErrorEvent",
    "HookPreToolEvent",
    "parse_sdk_event",
    "PromptParams",
    "PromptResult",
    "GetStateParams",
    "GetStateResult",
    "GetMessagesParams",
    "GetMessagesResult",
    "PermissionResponseParams",
    "PermissionAcknowledgedParams",
    "PermissionAcknowledgedResult",
    "DirectoryAccessResponseParams",
    "DirectoryAccessResponseResult",
    "DirectoryAccessAcknowledgedParams",
    "DirectoryAccessAcknowledgedResult",
    "ChangesDecisionAction",
    "ChangesDecisionParams",
    "ChangesDecisionError",
    "ChangesDecisionResult",
    "GetHistoryParams",
    "RPCHistoryEntry",
    "GetHistoryResult",
    "GetSessionParams",
    "RPCMessageToolCall",
    "RPCMessage",
    "GetSessionSuccessResult",
    "GetSessionFailureResult",
    "GetSessionResult",
    "SessionAttachParams",
    "SessionAttachResult",
    "YoloSetParams",
    "YoloSetResult",
    "VscodeMcpInputSchema",
    "VscodeMcpToolDescriptor",
    "McpSetVscodeToolsParams",
    "McpSetVscodeToolsResult",
    "McpInvokeResponseParams",
    "McpInvokeResponseResult",
    "LearnRecommendParams",
    "LearnAuditEntry",
    "LearnRecommendation",
    "LearnRecommendResult",
    "LearnUpdateEntry",
    "LearnUpdateResult",
    "LearnGenerateParams",
    "LearnGenerateResult",
    "ToolRegistryEntry",
    "ToolRegistryDiagnostic",
    "GetToolsRegistryResult",
    "SetContextCompactParams",
    "SetContextCompactResult",
    "ResetParams",
    "ResetResult",
    "BrowserHandoffCreateParams",
    "BrowserHandoffCreateResult",
    "BrowserHandoffAttachParams",
    "BrowserHandoffAttachResult",
    "BrowserHandoffAttachLatestParams",
    "BrowserHandoffAttachLatestResult",
    "AutomodeStartParams",
    "AutomodeStartResult",
    "AutomodeSessionStatus",
    "AutomodeCheckpoint",
    "AutomodeState",
    "AutomodeStatusParams",
    "AutomodeStatusResult",
    "AutomodePauseParams",
    "AutomodeOperationResult",
    "AutomodeResumeParams",
    "AutomodeResumeResult",
    "AutomodeCancelParams",
    "AutomodeCancelResult",
    "AutomodeGetLogParams",
    "AutomodeLogCheckpoint",
    "AutomodeIterationLog",
    "AutomodeGetLogResult",
    # Persistent goal types
    "GoalStatus",
    "GoalState",
    "QueuedGoal",
    "CompletedGoal",
    "GoalSnapshot",
    "GoalTemplateMetadata",
    "GoalTelemetry",
    "GoalMutationResult",
    "GoalFeatureDisabledResult",
    "GoalBudgetParams",
    "CreateGoalParams",
    "UpdateGoalParams",
    "GoalSnapshotResult",
    "GoalMutationRPCResult",
    "GoalTemplatesResult",
    # Feature types
    "FeatureFlagSettings",
    # Skills registry and MCP discovery types
    "CommunitySkill",
    "SkillRegistryCategory",
    "GetSkillsRegistryParams",
    "GetSkillsRegistryResult",
    "InstallSkillParams",
    "InstallSkillResult",
    "McpServerSummary",
    "McpListServersResult",
    "McpListToolsParams",
    "McpToolInfo",
    "McpListToolsResult",
    "McpGetServerConfigsResult",
    # Autoresearch types
    "AutoresearchSubagentOptions",
    "AutoresearchOptimizationDirection",
    "AutoresearchSecondaryObjective",
    "AutoresearchConstraint",
    "AutoresearchSamplingOptions",
    "AutoresearchRetentionOptions",
    "AutoresearchStartParams",
    "AutoresearchMetricAggregate",
    "AutoresearchEvaluationSample",
    "AutoresearchEvaluationRecord",
    "AutoresearchChecksResult",
    "AutoresearchExecutionResult",
    "AutoresearchConstraintResult",
    "AutoresearchDecisionRecord",
    "AutoresearchHistoryAttempt",
    "AutoresearchMaterializationState",
    "AutoresearchState",
    "AutoresearchStartResult",
    "AutoresearchStatusResult",
    "AutoresearchStopResult",
    "AutoresearchHistoryResult",
    "AutoresearchReplayParams",
    "AutoresearchReplayResult",
    "AutoresearchRescoreParams",
    "AutoresearchRescoreResult",
    "AutoresearchCompareParams",
    "AutoresearchComparisonSide",
    "AutoresearchComparison",
    "AutoresearchCompareResult",
    "AutoresearchParetoResult",
    "AutoresearchPinParams",
    "AutoresearchPinResult",
    "AutoresearchPruneParams",
    "AutoresearchPruneCandidate",
    "AutoresearchPruneResult",
    "AutoresearchEvent",
    "AutoresearchOperation",
    "AutoresearchOperationEvent",
    # Provider types
    "ProviderName",
    "AutohandEnvVars",
    "detect_provider_from_model",
    "validate_provider_config",
    "ProviderConfigError",
    # Skill types
    "SkillReference",
    "SkillSettings",
    "SkillSource",
    "SkillDefinition",
    "is_skill_file_path",
    "get_skill_name",
    "get_skill_path",
    # Permission types
    "PermissionMode",
    "PermissionRule",
    "PermissionSettings",
    # Context types
    "ContextUsage",
    "ContextSettings",
    # Session types
    "SessionStats",
    "SessionMetadata",
    "SessionSettings",
    "SessionType",
    # Tool types
    "Tool",
    # AGENTS.md types
    "AgentsMdSettings",
    "load_agents_md",
    "create_default_agents_md",
    # Model types
    "ModelInfo",
    "AgentInfo",
    "AccountInfo",
    "McpServerConfig",
    # Abort types
    "AbortParams",
    "AbortResult",
    # Version
    "__version__",
]

_ERROR_EXPORTS = {
    "AutohandSDKError",
    "RequestTimeoutError",
    "RPCError",
    "TransportError",
    "TransportNotStartedError",
}
_EXPORT_MODULES = {
    name: "autohand_sdk.types"
    for name in __all__
    if name
    not in {
        "__version__",
        "Agent",
        "AutohandSDK",
        "RPCClient",
        "Transport",
        *_ERROR_EXPORTS,
    }
}
_EXPORT_MODULES.update(
    {
        "Agent": "autohand_sdk.agent",
        "AutohandSDK": "autohand_sdk.sdk",
        "RPCClient": "autohand_sdk.rpc_client",
        "Transport": "autohand_sdk.transport",
        **dict.fromkeys(_ERROR_EXPORTS, "autohand_sdk.errors"),
    }
)


def __getattr__(name: str):
    """Load documented public exports on first access."""
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Include lazy public exports in interactive discovery."""
    return sorted({*globals(), *__all__})
