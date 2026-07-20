"""Type definitions for the Autohand SDK.

This module contains all Pydantic models and type definitions used throughout
the SDK, including configuration, events, and API parameters.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Literal, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

MIN_TEMPERATURE = 0.0
MAX_TEMPERATURE = 2.0

# =============================================================================
# Provider Types
# =============================================================================


class ProviderName(str, Enum):
    """Supported LLM providers."""

    AUTOHANDAI = "autohandai"
    OPENROUTER = "openrouter"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE = "azure"
    OLLAMA = "ollama"
    LLAMACPP = "llamacpp"
    MLX = "mlx"
    LLMGATEWAY = "llmgateway"
    ZAI = "zai"
    XAI = "xai"
    CEREBRAS = "cerebras"
    DEEPSEEK = "deepseek"
    VERTEXAI = "vertexai"
    NVIDIA = "nvidia"


class AutohandEnvVars(BaseModel):
    """AUTOHAND_ prefixed environment variables forwarded to CLI subprocess.

    These environment variables provide fine-grained control over CLI behavior
    when using the SDK programmatically.
    """

    model_config = ConfigDict(populate_by_name=True)

    AUTOHAND_DEBUG: str | None = Field(
        None, description="Enable debug logging mode ('1' to enable)"
    )
    AUTOHAND_HOME: str | None = Field(None, description="Base directory for all Autohand user data")
    AUTOHAND_API_URL: str | None = Field(
        None, description="API base URL for authentication and sync services"
    )
    AUTOHAND_CONFIG: str | None = Field(None, description="Config file path override")
    AUTOHAND_AI_API_KEY: str | None = Field(
        None, description="Autohand AI API key for SDK Cloud usage"
    )
    AUTOHAND_AI_BASE_URL: str | None = Field(None, description="Autohand AI base URL override")
    AUTOHAND_AI_PLAN: str | None = Field(
        None, description="Autohand AI plan style (cloud or local)"
    )
    AUTOHAND_CLIENT_NAME: str | None = Field(
        None, description="Client identifier for ACP extensions (e.g., 'zed', 'terminal')"
    )
    AUTOHAND_CLIENT_VERSION: str | None = Field(None, description="Client version string")
    AUTOHAND_CODE: str | None = Field(None, description="Auth code for headless setup")
    AUTOHAND_LOCALE: str | None = Field(None, description="Display language locale override")
    AUTOHAND_NO_BANNER: str | None = Field(
        None, description="Suppress startup banner ('1' to suppress)"
    )
    AUTOHAND_NON_INTERACTIVE: str | None = Field(
        None, description="Force non-interactive mode ('1' to enable)"
    )
    AUTOHAND_PERMISSION_CALLBACK_TIMEOUT: str | None = Field(
        None, description="Permission callback timeout in milliseconds"
    )
    AUTOHAND_PERMISSION_CALLBACK_URL: str | None = Field(
        None, description="Permission callback URL for external approval"
    )
    AUTOHAND_SECRET: str | None = Field(
        None, description="Company/enterprise secret for team features"
    )
    AUTOHAND_SHARE_URL: str | None = Field(None, description="Share API URL override")
    AUTOHAND_SKIP_PING: str | None = Field(
        None, description="Skip telemetry ping on startup ('1' to skip)"
    )
    AUTOHAND_SKIP_UPDATE_CHECK: str | None = Field(
        None, description="Skip version check on startup ('1' to skip)"
    )
    AUTOHAND_STREAM_TOOL_OUTPUT: str | None = Field(
        None, description="Stream tool output in real-time ('1' to enable)"
    )
    AUTOHAND_TERMINAL_REGIONS: str | None = Field(
        None, description="Disable terminal regions for box drawing ('0' to disable)"
    )
    AUTOHAND_THINKING_LEVEL: str | None = Field(
        None, description="Default thinking level (low, medium, high)"
    )
    AUTOHAND_TMUX_LAUNCHED: str | None = Field(
        None, description="TMUX session indicator ('1' when launched from tmux)"
    )
    AUTOHAND_YES: str | None = Field(
        None, description="Auto-confirm prompts without user interaction ('1' to enable)"
    )


def detect_provider_from_model(model: str) -> ProviderName | None:
    """Detect the provider based on model ID patterns.

    Args:
        model: The model ID to detect provider from.

    Returns:
        The detected ProviderName or None if not recognized.

    Examples:
        >>> detect_provider_from_model("claude-5-sonnet")
        ProviderName.ANTHROPIC
        >>> detect_provider_from_model("openrouter/quasar-alpha")
        ProviderName.OPENROUTER
    """
    model_lower = model.lower()

    if model_lower in {"fantail", "moa"} or model_lower.startswith("autohandai/"):
        return ProviderName.AUTOHANDAI

    # OpenRouter patterns
    if model_lower.startswith("openrouter/") or model_lower.startswith("or/"):
        return ProviderName.OPENROUTER

    # Z.ai patterns
    if "glm" in model_lower or "z-ai" in model_lower or model_lower.startswith("zai/"):
        return ProviderName.ZAI

    # Anthropic patterns
    if any(pattern in model_lower for pattern in ["claude", "anthropic"]):
        return ProviderName.ANTHROPIC

    # Azure patterns (must be before OpenAI since azure/gpt-4 would match OpenAI)
    if model_lower.startswith("azure/"):
        return ProviderName.AZURE

    # OpenAI patterns
    if any(pattern in model_lower for pattern in ["gpt-", "o1-", "o3-", "openai"]):
        return ProviderName.OPENAI

    # Ollama patterns - ollama/ prefix or typical Ollama model names with :
    if model_lower.startswith("ollama/") or ":" in model_lower:
        return ProviderName.OLLAMA

    if model_lower.startswith("mlx/"):
        return ProviderName.MLX

    if model_lower.startswith("llamacpp/") or model_lower.startswith("llama-cpp/"):
        return ProviderName.LLAMACPP

    if "llmgateway" in model_lower or model_lower.startswith("gateway/"):
        return ProviderName.LLMGATEWAY

    # xAI patterns
    if any(pattern in model_lower for pattern in ["grok", "xai"]):
        return ProviderName.XAI

    # Cerebras patterns
    if "cerebras" in model_lower:
        return ProviderName.CEREBRAS

    # DeepSeek patterns
    if "deepseek" in model_lower:
        return ProviderName.DEEPSEEK

    # Vertex AI patterns
    if "vertex" in model_lower or "gemini" in model_lower:
        return ProviderName.VERTEXAI

    # NVIDIA patterns
    if "nvidia" in model_lower or "nemotron" in model_lower:
        return ProviderName.NVIDIA

    return None


class ProviderConfigError(Exception):
    """Error raised when provider configuration is invalid."""

    pass


def validate_provider_config(provider: ProviderName, config: SDKConfig) -> None:
    """Validate provider-specific configuration.

    Args:
        provider: The provider to validate configuration for.
        config: The SDK configuration to validate.

    Raises:
        ProviderConfigError: If the configuration is invalid for the provider.
    """
    if provider == ProviderName.AZURE:
        if not config.azure_resource_name:
            raise ProviderConfigError("Azure provider requires 'azure_resource_name' configuration")
        if not config.azure_deployment_name:
            raise ProviderConfigError(
                "Azure provider requires 'azure_deployment_name' configuration"
            )

    elif provider == ProviderName.OPENAI:
        if config.openai_auth_mode == "api-key" and not config.api_key:
            raise ProviderConfigError("OpenAI provider with api-key auth mode requires 'api_key'")

    elif provider == ProviderName.AUTOHANDAI:
        if config.autohand_ai_plan != "local" and not config.api_key:
            raise ProviderConfigError("Autohand AI SDK Cloud usage requires 'api_key'")


# =============================================================================
# Skill Types
# =============================================================================

SkillReference: TypeAlias = str | dict[str, Any]


class SkillSource(BaseModel):
    """Source for discovering skills."""

    name: str
    url: str | None = None
    path: str | None = None


class SkillDefinition(BaseModel):
    """Definition of a skill with metadata."""

    name: str
    description: str
    version: str = "1.0.0"
    author: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_active: bool = True


class SkillSettings(BaseModel):
    """Skill settings for SDK configuration."""

    auto_skill: bool | None = Field(None, description="Enable automatic skill selection")
    skills: list[SkillReference] = Field(
        default_factory=list, description="Specific skills to load (by name or file path)"
    )
    sources: list[SkillSource] = Field(default_factory=list, description="Skill sources to search")
    install_missing: bool | None = Field(
        None, description="Whether to install missing skills from community"
    )


def is_skill_file_path(ref: SkillReference) -> bool:
    """Check if a skill reference is a file path.

    Args:
        ref: The skill reference to check.

    Returns:
        True if the reference is a file path, False otherwise.
    """
    if isinstance(ref, str):
        return "/" in ref or ref.endswith(".md")
    return False


def get_skill_name(ref: SkillReference) -> str:
    """Extract the skill name from a reference.

    Args:
        ref: The skill reference.

    Returns:
        The skill name.
    """
    if isinstance(ref, str):
        if is_skill_file_path(ref):
            # For file paths, use directory name or basename without extension
            parts = [p for p in ref.split("/") if p and p not in (".", "..")]
            name = parts[-1] if parts else "custom-skill"
            if name == "SKILL.md" and len(parts) > 1:
                name = parts[-2]
            return name.replace(".md", "").replace(".MD", "")
        return ref
    elif isinstance(ref, dict):
        name = ref.get("name", "custom-skill")
        return str(name)
    return "custom-skill"


def get_skill_path(ref: SkillReference) -> str | None:
    """Extract the file path from a skill reference.

    Args:
        ref: The skill reference.

    Returns:
        The file path if applicable, None otherwise.
    """
    if isinstance(ref, str) and is_skill_file_path(ref):
        return ref
    elif isinstance(ref, dict):
        return ref.get("path")
    return None


# =============================================================================
# Permission Types
# =============================================================================

PermissionMode = Literal[
    "default",
    "acceptEdits",
    "bypassPermissions",
    "plan",
    "dontAsk",
    "auto",
    "ask",
    "yolo",
    "interactive",
    "unrestricted",
    "restricted",
    "external",
]


class PermissionRule(BaseModel):
    """Rule for permission handling."""

    tool: str | None = None
    pattern: str | None = None
    decision: Literal["allow", "deny", "ask"] = "ask"


class PermissionSettings(BaseModel):
    """Permission settings for the SDK."""

    mode: PermissionMode | None = Field(None, description="Permission mode")
    allow_list: list[str] = Field(default_factory=list, description="Tools to always allow")
    deny_list: list[str] = Field(default_factory=list, description="Tools to always deny")
    rules: list[PermissionRule] = Field(default_factory=list, description="Permission rules")


# =============================================================================
# Context Types
# =============================================================================


class ContextUsage(BaseModel):
    """Context usage information."""

    tokens: int = Field(..., description="Current token count")
    limit: int | None = Field(None, description="Maximum token limit")
    percent: float | None = Field(None, description="Usage percentage")


class ContextSettings(BaseModel):
    """Context management settings."""

    context_compact: bool | None = Field(None, description="Enable context compaction")
    max_tokens: int | None = Field(None, description="Maximum context window in tokens", gt=0)
    compression_threshold: float | None = Field(
        None, description="Threshold for starting compression (0-1)", ge=0, le=1
    )
    summarization_threshold: float | None = Field(
        None, description="Threshold for starting summarization (0-1)", ge=0, le=1
    )


# =============================================================================
# Session Types
# =============================================================================

SessionType = Literal["interactive", "batch", "server"]


class SessionMetadata(BaseModel):
    """Metadata for a session."""

    session_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    model: str | None = None
    workspace: str | None = None


class SessionSettings(BaseModel):
    """Session management settings."""

    model_config = ConfigDict(populate_by_name=True)

    persist_session: bool | None = Field(None, description="Persist session to disk")
    session_id: str | None = Field(None, description="Session ID to resume")
    resume: bool | None = Field(None, description="Resume from last session")
    continue_: bool | None = Field(None, alias="continue", description="Continue from last session")
    session_path: str | None = Field(None, description="Session storage path")
    auto_save_interval: int | None = Field(None, description="Auto-save interval in seconds", gt=0)


class SessionStats(BaseModel):
    """Statistics for a session."""

    total_turns: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    duration_seconds: float = 0.0


# =============================================================================
# Tool Types
# =============================================================================


class Tool(str, Enum):
    """Available tools for the agent."""

    READ = "read"
    WRITE = "write"
    EDIT = "edit"
    BASH = "bash"
    BROWSE = "browse"
    GREP_SEARCH = "grep_search"
    LIST_DIR = "list_dir"


# =============================================================================
# AGENTS.md Types
# =============================================================================


class AgentsMdSettings(BaseModel):
    """Settings for AGENTS.md file."""

    enable: bool | None = Field(None, description="Enable AGENTS.md usage")
    create: bool | None = Field(None, description="Create AGENTS.md if it doesn't exist")
    path: str | None = Field(None, description="Path to AGENTS.md")
    auto_update: bool | None = Field(
        None, description="Auto-update AGENTS.md with discovered patterns"
    )
    include_tools: bool | None = Field(None, description="Include tools in AGENTS.md")
    include_commands: bool | None = Field(None, description="Include commands in AGENTS.md")
    include_skills: bool | None = Field(None, description="Include skills in AGENTS.md")
    include_conventions: bool | None = Field(None, description="Include conventions in AGENTS.md")


def load_agents_md(path: str | Path) -> AgentsMdSettings:
    """Load AGENTS.md settings from a file.

    Args:
        path: Path to the AGENTS.md file.

    Returns:
        The loaded settings.
    """
    # Implementation would parse the markdown file
    return AgentsMdSettings.model_validate({"path": str(path)})


def create_default_agents_md(path: str | Path) -> None:
    """Create a default AGENTS.md file.

    Args:
        path: Path where to create the file.
    """
    content = """# AGENTS.md

## Tools

- read
- write
- edit

## Commands

None

## Conventions

Follow the project's existing code style.
"""
    Path(path).write_text(content)


# =============================================================================
# Model Types
# =============================================================================


class ModelInfo(BaseModel):
    """Information about an available model."""

    id: str
    display_name: str
    provider: str | None = None
    context_window: int | None = None
    supports_vision: bool = False
    supports_tool_use: bool = True


class AgentInfo(BaseModel):
    """Information about an available agent/subagent."""

    name: str
    description: str | None = None
    version: str = "1.0.0"


class AccountInfo(BaseModel):
    """Account information."""

    email: str | None = None
    organization: str | None = None
    plan: str | None = None


class McpServerConfig(BaseModel):
    """Configuration for an MCP server."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    transport: Literal["stdio", "sse", "http"] | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    auto_connect: bool | None = Field(None, alias="autoConnect")


class CommunitySkill(BaseModel):
    """A skill published in the CLI community registry."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    description: str
    category: str
    tags: list[str] | None = None
    rating: float | None = None
    download_count: int | None = Field(None, alias="downloadCount")
    is_featured: bool | None = Field(None, alias="isFeatured")
    is_curated: bool | None = Field(None, alias="isCurated")


class SkillRegistryCategory(BaseModel):
    """A registry category and the number of matching skills."""

    name: str
    count: int


class GetSkillsRegistryParams(BaseModel):
    """Parameters for retrieving the community skill registry."""

    model_config = ConfigDict(populate_by_name=True)

    force_refresh: bool | None = Field(None, alias="forceRefresh")


class GetSkillsRegistryResult(BaseModel):
    """Typed result from ``autohand.getSkillsRegistry``."""

    success: bool
    skills: list[CommunitySkill]
    categories: list[SkillRegistryCategory]
    error: str | None = None


class InstallSkillParams(BaseModel):
    """Parameters for installing one registry skill."""

    model_config = ConfigDict(populate_by_name=True)

    skill_name: str = Field(..., alias="skillName")
    scope: Literal["user", "project"]
    force: bool | None = None


class InstallSkillResult(BaseModel):
    """Typed result from ``autohand.installSkill``."""

    model_config = ConfigDict(populate_by_name=True)

    success: bool
    skill_name: str | None = Field(None, alias="skillName")
    path: str | None = None
    error: str | None = None


class McpServerSummary(BaseModel):
    """Connection status for one known MCP server."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    status: str
    tool_count: int = Field(..., alias="toolCount")


class McpListServersResult(BaseModel):
    """Typed result from ``autohand.mcp.listServers``."""

    servers: list[McpServerSummary]


class McpListToolsParams(BaseModel):
    """Optional server filter for MCP tool discovery."""

    model_config = ConfigDict(populate_by_name=True)

    server_name: str | None = Field(None, alias="serverName")


class McpToolInfo(BaseModel):
    """A tool exposed by an MCP server."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str
    server_name: str = Field(..., alias="serverName")


class McpListToolsResult(BaseModel):
    """Typed result from ``autohand.mcp.listTools``."""

    tools: list[McpToolInfo]


class McpGetServerConfigsResult(BaseModel):
    """Typed result from ``autohand.mcp.getServerConfigs``."""

    configs: list[McpServerConfig]


# =============================================================================
# Autoresearch Types
# =============================================================================


def _snake_to_camel(value: str) -> str:
    """Convert a Python field name to the CLI's lower-camel-case spelling."""
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class GoalModel(BaseModel):
    """Base model for persistent-goal RPC values."""

    model_config = ConfigDict(
        alias_generator=_snake_to_camel,
        populate_by_name=True,
        extra="allow",
    )


GoalStatus: TypeAlias = Literal["active", "paused", "budgetLimited", "complete"]


class GoalState(GoalModel):
    """Active persistent-goal state."""

    goal_id: str
    objective: str
    status: GoalStatus
    token_budget: int | None = None
    time_budget_seconds: int | None = None
    min_tokens_before_wrap_up: int | None = None
    min_time_seconds_before_wrap_up: int | None = None
    tokens_used: int
    time_used_seconds: int
    created_at: int
    updated_at: int


class QueuedGoal(GoalModel):
    """Goal waiting for the active goal to finish."""

    queue_id: str
    objective: str
    token_budget: int | None = None
    time_budget_seconds: int | None = None
    min_tokens_before_wrap_up: int | None = None
    min_time_seconds_before_wrap_up: int | None = None
    source: Literal["command", "tool", "rpc", "cli"]
    template: str | None = None
    template_flags: dict[str, str] | None = None
    template_args: str | None = None
    created_at: int


class CompletedGoal(GoalModel):
    """Completed or budget-limited persistent goal."""

    goal_id: str
    objective: str
    status: Literal["complete", "budgetLimited"]
    tokens_used: int
    time_used_seconds: int
    created_at: int
    completed_at: int


class GoalSnapshot(GoalModel):
    """Current persistent-goal state, queue, and completion history."""

    version: Literal[1]
    goal: GoalState | None
    queue: list[QueuedGoal]
    completed: list[CompletedGoal]
    updated_at: int


class GoalTemplateMetadata(GoalModel):
    """Metadata for one reusable goal template."""

    name: str
    path: str
    description: str | None = None
    aliases: list[str]
    allow_commands: bool
    required_placeholders: list[str]
    required_flags: list[str]
    requires_args: bool


class GoalTelemetry(GoalModel):
    """Optional remaining-budget telemetry after a goal mutation."""

    time_remaining_seconds: int | None = None
    tokens_remaining: int | None = None
    completion_floor_met: bool | None = None


class GoalMutationResult(GoalModel):
    """Result of creating, updating, clearing, queuing, or starting a goal."""

    ok: bool
    goal: GoalState | None = None
    queue: list[QueuedGoal] = Field(default_factory=list)
    telemetry: GoalTelemetry | None = None
    message: str | None = None
    queued: list[QueuedGoal] | None = None
    started: QueuedGoal | None = None
    completed: CompletedGoal | None = None
    completed_run: list[CompletedGoal] | None = None
    dequeued: QueuedGoal | None = None
    removed: QueuedGoal | None = None


class GoalFeatureDisabledResult(GoalModel):
    """Returned when the persistent-goal feature is disabled."""

    ok: Literal[False]
    message: str


class GoalBudgetParams(GoalModel):
    """Shared persistent-goal budget options."""

    token_budget: int | None = Field(None, gt=0)
    time_budget_seconds: int | None = Field(None, gt=0)
    min_tokens_before_wrap_up: int | None = Field(None, ge=0)
    min_time_seconds_before_wrap_up: int | None = Field(None, ge=0)


class CreateGoalParams(GoalBudgetParams):
    """Parameters for creating or queueing a persistent goal."""

    objective: str


class UpdateGoalParams(GoalModel):
    """Parameters for updating the active persistent goal."""

    objective: str | None = None
    status: GoalStatus | None = None
    token_budget: int | None = Field(None, gt=0)
    time_budget_seconds: int | None = Field(None, gt=0)
    min_tokens_before_wrap_up: int | None = Field(None, ge=0)
    min_time_seconds_before_wrap_up: int | None = Field(None, ge=0)


QueueGoalParams: TypeAlias = CreateGoalParams
GoalSnapshotResult: TypeAlias = GoalSnapshot | GoalFeatureDisabledResult
GoalMutationRPCResult: TypeAlias = GoalMutationResult | GoalFeatureDisabledResult
GoalTemplatesResult: TypeAlias = list[GoalTemplateMetadata] | GoalFeatureDisabledResult


class AutoresearchModel(BaseModel):
    """Base model for forward-compatible autoresearch RPC values."""

    model_config = ConfigDict(
        alias_generator=_snake_to_camel,
        populate_by_name=True,
        extra="allow",
    )


AutoresearchOptimizationDirection: TypeAlias = Literal["lower", "higher"]


class AutoresearchSubagentOptions(AutoresearchModel):
    """Optional subagent participation in an autoresearch loop."""

    idea_generation: bool | None = None
    measurement_analysis: bool | None = None
    finalization: bool | None = None


class AutoresearchSecondaryObjective(AutoresearchModel):
    """A secondary metric optimized alongside the primary metric."""

    name: str
    unit: str
    direction: AutoresearchOptimizationDirection


class AutoresearchConstraint(AutoresearchModel):
    """A deterministic acceptance constraint for an autoresearch metric."""

    metric_name: str
    operator: Literal["<", "<=", ">", ">="]
    threshold: float


class AutoresearchSamplingOptions(AutoresearchModel):
    """Repeated-measurement sampling policy."""

    min_samples: int | None = Field(None, gt=0)
    max_samples: int | None = Field(None, gt=0)
    confidence_threshold: float | None = Field(None, ge=0, le=1)


class AutoresearchRetentionOptions(AutoresearchModel):
    """Artifact retention limits for the replay ledger."""

    max_artifact_bytes: int | None = Field(None, ge=0)
    max_artifact_age_days: int | None = Field(None, ge=0)


class AutoresearchStartParams(AutoresearchModel):
    """Parameters used to initialize or resume autoresearch."""

    objective: str
    max_iterations: int | None = Field(None, gt=0)
    timeout_ms: int | None = Field(None, gt=0)
    metric_name: str | None = None
    metric_unit: str | None = None
    direction: AutoresearchOptimizationDirection | None = None
    measure_command: str | None = None
    measure_script: str | None = None
    checks_command: str | None = None
    checks_script: str | None = None
    files_in_scope: list[str] | None = None
    subagents: AutoresearchSubagentOptions | None = None
    secondary_objectives: list[AutoresearchSecondaryObjective] | None = None
    constraints: list[AutoresearchConstraint] | None = None
    sampling: AutoresearchSamplingOptions | None = None
    retention: AutoresearchRetentionOptions | None = None
    environment_allowlist: list[str] | None = None


class AutoresearchMetricAggregate(AutoresearchModel):
    """Robust aggregate for one measured metric."""

    median: float
    mad: float
    sample_count: int


class AutoresearchEvaluationSample(AutoresearchModel):
    """One immutable benchmark sample."""

    sequence: int
    metrics: dict[str, float]
    output_object: str
    duration_ms: int
    timestamp: str


class AutoresearchChecksResult(AutoresearchModel):
    """Deterministic checks attached to an evaluation."""

    passed: bool
    output_object: str | None = None


class AutoresearchExecutionResult(AutoresearchModel):
    """Execution outcome attached to an evaluation."""

    outcome: Literal["passed", "benchmark_failed", "checks_failed", "cancelled"]
    error: str | None = None
    output_object: str | None = None


class AutoresearchEvaluationRecord(AutoresearchModel):
    """Immutable replayable evaluation record."""

    schema_version: Literal[1]
    type: Literal["evaluation"]
    id: str
    attempt_id: str
    timestamp: str
    context: dict[str, object]
    evaluator_mode: Literal["original", "current"]
    samples: list[AutoresearchEvaluationSample]
    aggregates: dict[str, AutoresearchMetricAggregate]
    checks: AutoresearchChecksResult
    execution: AutoresearchExecutionResult
    drift_warnings: list[str]


class AutoresearchConstraintResult(AutoresearchConstraint):
    """Observed result for a configured acceptance constraint."""

    conservative_value: float
    passed: bool
    conclusive: bool


class AutoresearchDecisionRecord(AutoresearchModel):
    """Immutable policy decision derived from an evaluation."""

    schema_version: Literal[1]
    type: Literal["decision"]
    id: str
    attempt_id: str
    timestamp: str
    context: dict[str, object]
    policy_version: str
    evaluation_id: str
    source: Literal["original", "replay", "rescore"]
    constraint_results: list[AutoresearchConstraintResult]
    primary_improvement: float
    confidence: float
    outcome: Literal["accepted", "rejected", "inconclusive", "checks_failed", "crashed"]
    materialized: bool
    explanation: str


AutoresearchMaterializationState: TypeAlias = Literal[
    "baseline", "committed", "retained", "reverted", "none"
]


class AutoresearchHistoryAttempt(AutoresearchModel):
    """An attempt listed in the replayable autoresearch history."""

    attempt_id: str
    description: str
    timestamp: str
    legacy: bool
    replayable: bool
    pinned: bool
    latest_evaluation: AutoresearchEvaluationRecord | None = None
    latest_decision: AutoresearchDecisionRecord | None = None
    materialization: AutoresearchMaterializationState


class AutoresearchState(AutoresearchModel):
    """Persisted state for an autoresearch session."""

    active: bool
    goal: str
    iteration: int
    max_iterations: int


class AutoresearchStartResult(AutoresearchModel):
    """Result from initializing or resuming autoresearch."""

    success: bool
    message: str | None = None
    instruction: str | None = None
    active: bool | None = None
    state: AutoresearchState | None = None
    status_text: str | None = None
    runs_logged: int | None = None
    attempts: list[AutoresearchHistoryAttempt] | None = None
    pareto_attempt_ids: list[str] | None = None
    error: str | None = None


class AutoresearchStatusResult(AutoresearchModel):
    """Current autoresearch status and ledger summary."""

    success: bool
    active: bool
    state: AutoresearchState | None = None
    status_text: str
    runs_logged: int
    attempts: list[AutoresearchHistoryAttempt] | None = None
    pareto_attempt_ids: list[str] | None = None
    error: str | None = None


class AutoresearchStopResult(AutoresearchModel):
    """Result from pausing autoresearch without deleting state."""

    success: bool
    message: str | None = None
    active: bool | None = None
    state: AutoresearchState | None = None
    status_text: str | None = None
    runs_logged: int | None = None
    attempts: list[AutoresearchHistoryAttempt] | None = None
    pareto_attempt_ids: list[str] | None = None
    error: str | None = None


class AutoresearchHistoryResult(AutoresearchModel):
    """Result containing all immutable autoresearch attempts."""

    success: bool
    attempts: list[AutoresearchHistoryAttempt]
    error: str | None = None


class AutoresearchReplayParams(AutoresearchModel):
    """Parameters for replaying an attempt in an isolated worktree."""

    attempt_id: str
    evaluator: Literal["original", "current"] | None = None


class AutoresearchReplayResult(AutoresearchModel):
    """Result from replaying one autoresearch attempt."""

    success: bool
    attempt_id: str | None = None
    evaluator_mode: Literal["original", "current"] | None = None
    metrics: dict[str, float] | None = None
    samples: list[AutoresearchEvaluationSample] | None = None
    decision: AutoresearchDecisionRecord | None = None
    drift_warnings: list[str] | None = None
    error: str | None = None


class AutoresearchRescoreParams(AutoresearchModel):
    """Parameters for rescoring either one attempt or the complete ledger."""

    attempt_id: str | None = None
    all: bool | None = None

    @model_validator(mode="after")
    def validate_target(self) -> AutoresearchRescoreParams:
        """Require exactly one of ``attempt_id`` or ``all=True``."""
        if (self.attempt_id is None) == (self.all is not True):
            raise ValueError("Provide exactly one of 'attempt_id' or 'all=True'")
        return self


class AutoresearchRescoreResult(AutoresearchModel):
    """Result from applying current policy to stored measurements."""

    success: bool
    decisions: list[AutoresearchDecisionRecord]
    error: str | None = None


class AutoresearchCompareParams(AutoresearchModel):
    """Parameters for comparing two autoresearch attempts."""

    left_attempt_id: str
    right_attempt_id: str


class AutoresearchComparisonSide(AutoresearchModel):
    """One side of an autoresearch comparison."""

    attempt_id: str
    samples: list[AutoresearchEvaluationSample]
    aggregates: dict[str, AutoresearchMetricAggregate]
    checks: AutoresearchChecksResult
    execution: AutoresearchExecutionResult
    decision: AutoresearchDecisionRecord | None = None


class AutoresearchComparison(AutoresearchModel):
    """Side-by-side comparison of two attempts."""

    left: AutoresearchComparisonSide
    right: AutoresearchComparisonSide


class AutoresearchCompareResult(AutoresearchModel):
    """Result from comparing two attempts."""

    success: bool
    comparison: AutoresearchComparison | None = None
    error: str | None = None


class AutoresearchParetoResult(AutoresearchModel):
    """Constraint-passing, non-dominated attempt identifiers."""

    success: bool
    attempt_ids: list[str]
    error: str | None = None


class AutoresearchPinParams(AutoresearchModel):
    """Parameters for changing an attempt's retention pin."""

    attempt_id: str
    pinned: bool


class AutoresearchPinResult(AutoresearchModel):
    """Result from changing an attempt's retention pin."""

    success: bool
    attempt_id: str
    pinned: bool
    error: str | None = None


class AutoresearchPruneParams(AutoresearchModel):
    """Parameters for previewing or applying artifact pruning."""

    dry_run: bool | None = None
    yes: bool | None = None


class AutoresearchPruneCandidate(AutoresearchModel):
    """One candidate in an autoresearch artifact prune plan."""

    attempt_id: str
    objects: list[str]
    bytes: int
    protected: bool
    reason: str


class AutoresearchPruneResult(AutoresearchModel):
    """Result from previewing or applying artifact pruning."""

    success: bool
    applied: bool
    candidates: list[AutoresearchPruneCandidate]
    bytes_freed: int
    remaining_bytes: int
    error: str | None = None


# =============================================================================
# Event Types
# =============================================================================


class AgentStartEvent(BaseModel):
    """Event emitted when the agent starts."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal["agent_start"] = "agent_start"
    session_id: str = Field(..., alias="sessionId")
    model: str | None = None
    timestamp: str | None = None


class AgentEndEvent(BaseModel):
    """Event emitted when the agent ends."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal["agent_end"] = "agent_end"
    session_id: str = Field(..., alias="sessionId")
    reason: str | None = None
    timestamp: str | None = None


class MessageUpdateEvent(BaseModel):
    """Event emitted when message content is updated."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal["message_update"] = "message_update"
    delta: str | None = None
    content: str | None = None
    message_id: str | None = Field(None, alias="messageId")


class MessageEndEvent(BaseModel):
    """Event emitted when a message is complete."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal["message_end"] = "message_end"
    content: str | None = None
    message_id: str | None = Field(None, alias="messageId")


class ToolStartEvent(BaseModel):
    """Event emitted when a tool starts."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal["tool_start"] = "tool_start"
    tool_name: str = Field(..., alias="toolName")
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolUpdateEvent(BaseModel):
    """Event emitted when tool output is updated."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal["tool_update"] = "tool_update"
    tool_name: str = Field(..., alias="toolName")
    output: str


class ToolEndEvent(BaseModel):
    """Event emitted when a tool ends."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal["tool_end"] = "tool_end"
    tool_name: str = Field(..., alias="toolName")
    result: Any | None = None


class PermissionRequestEvent(BaseModel):
    """Event emitted when permission is requested."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal["permission_request"] = "permission_request"
    request_id: str = Field(..., alias="requestId")
    tool: str
    description: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ErrorEvent(BaseModel):
    """Event emitted when an error occurs."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    type: Literal["error"] = "error"
    message: str
    code: str | int | None = None
    details: dict[str, Any] | None = None


class AutoresearchEvent(AutoresearchModel):
    """Autoresearch session lifecycle notification."""

    type: Literal["autoresearch"] = "autoresearch"
    phase: Literal["start", "status", "pause"]
    active: bool
    goal: str | None = None
    iteration: int | None = None
    max_iterations: int | None = None
    runs_logged: int
    status_text: str
    subcommand: Literal["start", "resume", "status", "stop"]
    message: str | None = None
    timestamp: str


AutoresearchOperation: TypeAlias = Literal[
    "history", "replay", "rescore", "compare", "pareto", "pin", "prune"
]


class AutoresearchOperationEvent(AutoresearchModel):
    """Notification emitted by a replay-ledger operation."""

    type: Literal["autoresearch"] = "autoresearch"
    operation: AutoresearchOperation
    phase: Literal["started", "completed", "failed"]
    attempt_id: str | None = None
    success: bool
    applied: bool | None = None
    error: str | None = None
    timestamp: str


TypedSDKEvent: TypeAlias = (
    AgentStartEvent
    | AgentEndEvent
    | MessageUpdateEvent
    | MessageEndEvent
    | ToolStartEvent
    | ToolUpdateEvent
    | ToolEndEvent
    | PermissionRequestEvent
    | AutoresearchEvent
    | AutoresearchOperationEvent
    | ErrorEvent
)
SDKEvent: TypeAlias = dict[str, Any]

EVENT_MODEL_BY_TYPE: dict[str, type[BaseModel]] = {
    "agent_start": AgentStartEvent,
    "agent_end": AgentEndEvent,
    "message_update": MessageUpdateEvent,
    "message_end": MessageEndEvent,
    "tool_start": ToolStartEvent,
    "tool_update": ToolUpdateEvent,
    "tool_end": ToolEndEvent,
    "permission_request": PermissionRequestEvent,
    "error": ErrorEvent,
}


def parse_sdk_event(event: SDKEvent) -> TypedSDKEvent | SDKEvent:
    """Parse a raw SDK event dictionary into a typed event model when possible.

    Unknown event types and known events that are missing CLI-specific required
    fields are returned unchanged so callers can opt into typing without losing
    access to new CLI notifications.
    """
    event_type = event.get("type")
    if event_type == "autoresearch":
        model: type[BaseModel] | None = (
            AutoresearchOperationEvent if "operation" in event else AutoresearchEvent
        )
    else:
        model = EVENT_MODEL_BY_TYPE.get(event_type) if isinstance(event_type, str) else None
    if model is None:
        return event
    try:
        return cast(TypedSDKEvent, model.model_validate(event))
    except ValidationError:
        return event


# =============================================================================
# Method Parameter Types
# =============================================================================


class RPCContractModel(BaseModel):
    """Base model for lower-camel-case RPC contracts."""

    model_config = ConfigDict(
        alias_generator=_snake_to_camel,
        populate_by_name=True,
        extra="allow",
    )


class ResetParams(RPCContractModel):
    """Parameters for resetting the conversation context."""


class ResetResult(RPCContractModel):
    """Result from resetting the conversation context."""

    session_id: str


class BrowserHandoffCreateParams(RPCContractModel):
    """Parameters for creating a browser handoff."""

    extension_id: str | None = None
    install_url: str | None = None


class BrowserHandoffCreateResult(RPCContractModel):
    """A newly-created browser handoff token and launch URL."""

    token: str
    session_id: str
    workspace_root: str
    created_at: str
    expires_at: str
    url: str


class BrowserHandoffAttachParams(RPCContractModel):
    """Parameters for attaching a browser handoff."""

    token: str = Field(..., min_length=1)


class BrowserHandoffAttachResult(RPCContractModel):
    """Result from attaching a browser handoff session."""

    success: bool
    session_id: str | None = None
    workspace_root: str | None = None
    message_count: int | None = None


class BrowserHandoffAttachLatestParams(RPCContractModel):
    """Parameters for attaching the latest browser handoff."""


BrowserHandoffAttachLatestResult: TypeAlias = BrowserHandoffAttachResult


class AutomodeStartParams(RPCContractModel):
    """Parameters for starting autonomous execution."""

    prompt: str
    max_iterations: int | None = None
    completion_promise: str | None = None
    use_worktree: bool | None = None
    checkpoint_interval: int | None = None
    max_runtime: int | float | None = None
    max_cost: int | float | None = None


class AutomodeStartResult(RPCContractModel):
    """Result from starting autonomous execution."""

    success: bool
    session_id: str | None = None
    error: str | None = None


AutomodeSessionStatus: TypeAlias = Literal[
    "running",
    "paused",
    "completed",
    "cancelled",
    "failed",
]


class AutomodeCheckpoint(RPCContractModel):
    """Latest source-control checkpoint for an auto-mode session."""

    commit: str
    message: str
    timestamp: str


class AutomodeState(RPCContractModel):
    """Detailed state for an active or completed auto-mode session."""

    session_id: str
    status: AutomodeSessionStatus
    current_iteration: int
    max_iterations: int
    files_created: int
    files_modified: int
    branch: str | None = None
    last_checkpoint: AutomodeCheckpoint | None = None


class AutomodeStatusParams(RPCContractModel):
    """Parameters for reading auto-mode status."""


class AutomodeStatusResult(RPCContractModel):
    """Current autonomous execution status."""

    active: bool
    paused: bool
    state: AutomodeState | None = None


class AutomodePauseParams(RPCContractModel):
    """Parameters for pausing auto-mode."""


class AutomodeOperationResult(RPCContractModel):
    """Result from an auto-mode control operation."""

    success: bool
    error: str | None = None


class AutomodeResumeParams(RPCContractModel):
    """Parameters for resuming auto-mode."""


AutomodeResumeResult: TypeAlias = AutomodeOperationResult


class AutomodeCancelParams(RPCContractModel):
    """Parameters for cancelling auto-mode."""

    reason: str | None = None


AutomodeCancelResult: TypeAlias = AutomodeOperationResult


class PromptParams(BaseModel):
    """Parameters for the prompt method."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    message: str = Field(..., description="The message to send to the agent")
    context: dict[str, Any] | None = Field(
        None, description="Optional context including files and selection"
    )
    images: list[dict[str, Any]] | None = Field(None, description="Optional image attachments")
    thinking_level: Literal["none", "normal", "extended"] | None = Field(
        None,
        alias="thinkingLevel",
        description="Optional thinking depth level",
    )


class PromptResult(BaseModel):
    """Result from a prompt operation."""

    message_id: str | None = None
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class GetStateParams(BaseModel):
    """Parameters for getting agent state."""

    model_config = ConfigDict(populate_by_name=True)

    include_context: bool | None = Field(
        None,
        alias="includeContext",
        description="Whether to include context information",
    )


class GetStateResult(BaseModel):
    """Result from getting agent state."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    status: Literal["idle", "processing", "waiting_permission"]
    session_id: str | None = Field(None, alias="sessionId")
    model: str
    workspace: str
    context_percent: float | None = Field(None, alias="contextPercent")
    message_count: int = Field(0, alias="messageCount")


class GetMessagesParams(BaseModel):
    """Parameters for getting messages."""

    model_config = ConfigDict(populate_by_name=True)

    limit: int | None = Field(None, description="Maximum number of messages to return")
    before: str | None = Field(None, description="Return messages before this message ID")


class GetMessagesResult(BaseModel):
    """Result from getting messages."""

    messages: list[dict[str, Any]]


class PermissionResponseParams(BaseModel):
    """Parameters for responding to a permission request."""

    model_config = ConfigDict(populate_by_name=True)

    request_id: str = Field(..., alias="requestId", description="The permission request ID")
    decision: Literal["allow", "deny"] | str | None = Field(None, description="The decision")
    allowed: bool | None = Field(None, description="Whether the request is allowed")
    alternative: str | None = Field(None, description="Alternative command if denying")
    remember: bool | None = Field(None, description="Whether to remember this decision")


class AbortParams(BaseModel):
    """Parameters for aborting an operation."""

    reason: str | None = Field(None, description="Reason for aborting")


class AbortResult(BaseModel):
    """Result from aborting an operation."""

    success: bool = True
    message: str | None = None


class FeatureFlagSettings(BaseModel):
    """Current CLI feature and experiment settings."""

    model_config = ConfigDict(
        alias_generator=_snake_to_camel,
        populate_by_name=True,
        extra="allow",
    )

    environment: str | None = None
    remote_overrides: dict[str, Literal["off"]] | None = None
    usage_v2: bool | None = None
    aws_bedrock_provider: bool | None = None
    slash_goal: bool | None = None
    token_usage_status: bool | None = None
    experimental_fork: bool | None = None
    experimental_clone: bool | None = None
    experimental_handoff: bool | None = None


# =============================================================================
# Main Configuration
# =============================================================================


class SDKConfig(BaseModel):
    """Configuration for the Autohand SDK.

    This is the main configuration class that controls all aspects of the SDK's
    behavior, from basic settings to provider-specific options.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
    )

    # Basic Configuration
    cwd: str | None = Field(
        None, description="Working directory for the CLI (defaults to current directory)"
    )
    cli_path: str | None = Field(
        None, description="Path to CLI binary (auto-detected if not provided)"
    )
    debug: bool | None = Field(None, description="Enable debug logging")
    timeout: int | None = Field(
        None, description="Timeout for requests in milliseconds (default: 300000)", gt=0
    )
    startup_check: bool = Field(
        True, description="Probe the CLI with getState after subprocess startup"
    )
    plan_mode: bool | None = Field(None, description="Enable or disable plan mode after startup")

    # Provider Configuration
    model: str | None = Field(
        None, description="Model to use (provider is auto-detected from model ID)"
    )
    fallback_model: str | None = Field(None, description="Fallback model if primary fails")
    max_turns: int | None = Field(None, description="Maximum number of turns", gt=0)
    max_budget_usd: float | None = Field(None, description="Maximum budget in USD", ge=0)
    temperature: float | None = Field(
        None, description="Sampling temperature (0.0 to 2.0)", ge=0.0, le=2.0
    )

    # Provider-specific settings
    provider: ProviderName | None = Field(
        None, description="Provider name (if not provided, auto-detected from model ID)"
    )
    api_key: str | None = Field(None, description="API key for the provider")
    base_url: str | None = Field(None, description="Base URL for the provider API")
    autohand_ai_plan: Literal["cloud", "local"] | None = Field(
        None, description="Autohand AI plan style"
    )

    # OpenAI-specific options
    openai_auth_mode: Literal["api-key", "chatgpt"] | None = Field(
        None, description="OpenAI authentication mode"
    )
    reasoning_effort: Literal["low", "medium", "high"] | None = Field(
        None, description="OpenAI reasoning effort level (for o1 models)"
    )
    chatgpt_access_token: str | None = Field(None, description="OpenAI ChatGPT access token")
    chatgpt_account_id: str | None = Field(None, description="OpenAI ChatGPT account ID")

    # Azure-specific options
    azure_auth_method: Literal["api-key", "entra-id", "managed-identity"] | None = Field(
        None, description="Azure authentication method"
    )
    azure_tenant_id: str | None = Field(None, description="Azure tenant ID (for entra-id auth)")
    azure_client_id: str | None = Field(None, description="Azure client ID (for entra-id auth)")
    azure_client_secret: str | None = Field(
        None, description="Azure client secret (for entra-id auth)"
    )
    azure_resource_name: str | None = Field(None, description="Azure resource name")
    azure_deployment_name: str | None = Field(None, description="Azure deployment name")

    # Execution settings
    auto_mode: bool | None = Field(None, description="Enable auto-mode for autonomous execution")
    unrestricted: bool | None = Field(None, description="Run in unrestricted mode")
    auto_commit: bool | None = Field(
        None, description="Enable auto-commit with an LLM-generated message"
    )
    bare: bool | None = Field(None, description="Start the minimal explicit runtime")
    idle_logout: bool | None = Field(None, description="Keep authenticated idle logout enabled")
    max_iterations: int | None = Field(
        None, description="Maximum number of iterations in auto-mode", gt=0
    )
    max_runtime: int | None = Field(None, description="Maximum runtime in minutes", gt=0)
    max_cost: float | None = Field(None, description="Maximum API cost in dollars", ge=0)

    # System prompt settings
    sys_prompt: str | None = Field(None, description="System prompt (inline string or file path)")
    system_prompt_file: str | None = Field(None, description="File that replaces the system prompt")
    append_sys_prompt: str | None = Field(None, description="Append to system prompt")
    append_system_prompt_file: str | None = Field(
        None, description="File appended to the system prompt"
    )

    # YOLO (auto-approve) settings
    yolo: str | None = Field(None, description="Auto-approve tool calls matching pattern")
    yolo_timeout: int | None = Field(
        None, description="Timeout in seconds for auto-approve mode", gt=0
    )

    # Additional directories
    additional_directories: list[str] | None = Field(
        None, description="Additional directories to add to workspace"
    )
    add_dir: list[str] | None = Field(None, description="Additional directories (alias)")

    # Extra CLI arguments
    extra_args: list[str] | None = Field(None, description="Additional CLI arguments")

    # Environment variables
    env_vars: AutohandEnvVars | None = Field(
        None, description="Environment variables to forward to CLI subprocess"
    )

    # Skills configuration
    skills: SkillSettings | None = Field(None, description="Skill settings")
    skill_refs: list[SkillReference] | None = Field(
        None, description="Direct skill references (convenience)"
    )
    auto_skill: bool | None = Field(
        None, description="Enable auto-skill for automatic skill selection (legacy)"
    )
    copy_skill_files: bool = Field(
        True, description="Copy local skill files into ~/.autohand/skills before startup"
    )

    # Permissions configuration
    permissions: PermissionSettings | None = Field(None, description="Permission settings")
    permission_mode: PermissionMode | None = Field(None, description="Permission mode (legacy)")

    # Context configuration
    context: ContextSettings | None = Field(None, description="Context settings")
    context_compact: bool | None = Field(None, description="Enable context compaction (legacy)")

    # Session configuration
    session: SessionSettings | None = Field(None, description="Session settings")
    persist_session: bool | None = Field(None, description="Persist session to disk (legacy)")
    session_id: str | None = Field(None, description="Session ID to resume (legacy)")
    resume: bool | None = Field(None, description="Resume from last session (legacy)")
    continue_: bool | None = Field(
        None, alias="continue", description="Continue from last session (legacy)"
    )
    fork: str | None = Field(None, description="Fork an existing session before startup")

    # Runtime integration configuration
    display_language: str | None = Field(None, description="CLI display language locale")
    mcp_config: str | None = Field(None, description="Explicit MCP config file")
    agents: str | None = Field(None, description="Inline agents JSON or external agents directory")
    plugin_dir: str | None = Field(None, description="Explicit plugin or meta-tool directory")
    features: FeatureFlagSettings | None = Field(
        None, description="CLI feature settings applied at startup"
    )

    # AGENTS.md configuration
    agents_md: AgentsMdSettings | None = Field(None, description="AGENTS.md settings")
    agents_md_enable: bool | None = Field(None, description="Enable AGENTS.md usage (legacy)")
    agents_md_create: bool | None = Field(
        None, description="Create AGENTS.md if it doesn't exist (legacy)"
    )

    # Port for local provider
    port: int | None = Field(None, description="Port for local provider")

    @field_validator("cwd")
    @classmethod
    def validate_cwd(cls, v: str | None) -> str | None:
        """Validate and normalize the working directory."""
        if v is None:
            return None
        return str(Path(v).expanduser().resolve())

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v: float | None) -> float | None:
        """Validate temperature is within valid range."""
        if v is not None and (v < MIN_TEMPERATURE or v > MAX_TEMPERATURE):
            raise ValueError("Temperature must be between 0.0 and 2.0")
        return v

    @model_validator(mode="after")
    def validate_provider(self) -> SDKConfig:
        """Auto-detect provider from model if not explicitly set."""
        if self.provider is None and self.model is not None:
            detected = detect_provider_from_model(self.model)
            if detected is not None:
                self.provider = detected
        return self
