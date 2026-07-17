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

from autohand_sdk.errors import (
    AutohandSDKError,
    RequestTimeoutError,
    RPCError,
    TransportError,
    TransportNotStartedError,
)
from autohand_sdk.rpc_client import RPCClient
from autohand_sdk.sdk import AutohandSDK
from autohand_sdk.transport import Transport
from autohand_sdk.types import (
    # Abort types
    AbortParams,
    AbortResult,
    AccountInfo,
    AgentInfo,
    # AGENTS.md types
    AgentsMdSettings,
    AutohandEnvVars,
    AutoresearchChecksResult,
    AutoresearchCompareParams,
    AutoresearchCompareResult,
    AutoresearchComparison,
    AutoresearchComparisonSide,
    AutoresearchConstraint,
    AutoresearchConstraintResult,
    AutoresearchDecisionRecord,
    AutoresearchEvaluationRecord,
    AutoresearchEvaluationSample,
    AutoresearchEvent,
    AutoresearchExecutionResult,
    AutoresearchHistoryAttempt,
    AutoresearchHistoryResult,
    AutoresearchMaterializationState,
    AutoresearchMetricAggregate,
    AutoresearchOperation,
    AutoresearchOperationEvent,
    AutoresearchOptimizationDirection,
    AutoresearchParetoResult,
    AutoresearchPinParams,
    AutoresearchPinResult,
    AutoresearchPruneCandidate,
    AutoresearchPruneParams,
    AutoresearchPruneResult,
    AutoresearchReplayParams,
    AutoresearchReplayResult,
    AutoresearchRescoreParams,
    AutoresearchRescoreResult,
    AutoresearchRetentionOptions,
    AutoresearchSamplingOptions,
    AutoresearchSecondaryObjective,
    AutoresearchStartParams,
    AutoresearchStartResult,
    AutoresearchState,
    AutoresearchStatusResult,
    AutoresearchStopResult,
    AutoresearchSubagentOptions,
    ContextSettings,
    # Context types
    ContextUsage,
    GetMessagesParams,
    GetMessagesResult,
    GetStateParams,
    GetStateResult,
    McpServerConfig,
    # Model types
    ModelInfo,
    # Permission types
    PermissionMode,
    PermissionResponseParams,
    PermissionRule,
    PermissionSettings,
    PromptParams,
    PromptResult,
    ProviderConfigError,
    # Provider types
    ProviderName,
    # Core types
    SDKConfig,
    SDKEvent,
    SessionMetadata,
    SessionSettings,
    # Session types
    SessionStats,
    SessionType,
    SkillDefinition,
    # Skill types
    SkillReference,
    SkillSettings,
    SkillSource,
    # Tool types
    Tool,
    TypedSDKEvent,
    create_default_agents_md,
    detect_provider_from_model,
    get_skill_name,
    get_skill_path,
    is_skill_file_path,
    load_agents_md,
    parse_sdk_event,
    validate_provider_config,
)

__version__ = "0.1.0"
__all__ = [
    # Main classes
    "AutohandSDK",
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
    "parse_sdk_event",
    "PromptParams",
    "PromptResult",
    "GetStateParams",
    "GetStateResult",
    "GetMessagesParams",
    "GetMessagesResult",
    "PermissionResponseParams",
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
