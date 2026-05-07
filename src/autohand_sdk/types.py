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

    AUTOHAND_DEBUG: str | None = Field(None, description="Enable debug logging mode ('1' to enable)")
    AUTOHAND_HOME: str | None = Field(None, description="Base directory for all Autohand user data")
    AUTOHAND_API_URL: str | None = Field(None, description="API base URL for authentication and sync services")
    AUTOHAND_CONFIG: str | None = Field(None, description="Config file path override")
    AUTOHAND_CLIENT_NAME: str | None = Field(None, description="Client identifier for ACP extensions (e.g., 'zed', 'terminal')")
    AUTOHAND_CLIENT_VERSION: str | None = Field(None, description="Client version string")
    AUTOHAND_CODE: str | None = Field(None, description="Auth code for headless setup")
    AUTOHAND_LOCALE: str | None = Field(None, description="Display language locale override")
    AUTOHAND_NO_BANNER: str | None = Field(None, description="Suppress startup banner ('1' to suppress)")
    AUTOHAND_NON_INTERACTIVE: str | None = Field(None, description="Force non-interactive mode ('1' to enable)")
    AUTOHAND_PERMISSION_CALLBACK_TIMEOUT: str | None = Field(None, description="Permission callback timeout in milliseconds")
    AUTOHAND_PERMISSION_CALLBACK_URL: str | None = Field(None, description="Permission callback URL for external approval")
    AUTOHAND_SECRET: str | None = Field(None, description="Company/enterprise secret for team features")
    AUTOHAND_SHARE_URL: str | None = Field(None, description="Share API URL override")
    AUTOHAND_SKIP_PING: str | None = Field(None, description="Skip telemetry ping on startup ('1' to skip)")
    AUTOHAND_SKIP_UPDATE_CHECK: str | None = Field(None, description="Skip version check on startup ('1' to skip)")
    AUTOHAND_STREAM_TOOL_OUTPUT: str | None = Field(None, description="Stream tool output in real-time ('1' to enable)")
    AUTOHAND_TERMINAL_REGIONS: str | None = Field(None, description="Disable terminal regions for box drawing ('0' to disable)")
    AUTOHAND_THINKING_LEVEL: str | None = Field(None, description="Default thinking level (low, medium, high)")
    AUTOHAND_TMUX_LAUNCHED: str | None = Field(None, description="TMUX session indicator ('1' when launched from tmux)")
    AUTOHAND_YES: str | None = Field(None, description="Auto-confirm prompts without user interaction ('1' to enable)")


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
            raise ProviderConfigError("Azure provider requires 'azure_deployment_name' configuration")

    elif provider == ProviderName.OPENAI:
        if config.openai_auth_mode == "api-key" and not config.api_key:
            raise ProviderConfigError("OpenAI provider with api-key auth mode requires 'api_key'")

    # Add more provider-specific validation as needed


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
    skills: list[SkillReference] = Field(default_factory=list, description="Specific skills to load (by name or file path)")
    sources: list[SkillSource] = Field(default_factory=list, description="Skill sources to search")
    install_missing: bool | None = Field(None, description="Whether to install missing skills from community")


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
    compression_threshold: float | None = Field(None, description="Threshold for starting compression (0-1)", ge=0, le=1)
    summarization_threshold: float | None = Field(None, description="Threshold for starting summarization (0-1)", ge=0, le=1)


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
    auto_update: bool | None = Field(None, description="Auto-update AGENTS.md with discovered patterns")
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

    name: str
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


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


TypedSDKEvent: TypeAlias = (
    AgentStartEvent
    | AgentEndEvent
    | MessageUpdateEvent
    | MessageEndEvent
    | ToolStartEvent
    | ToolUpdateEvent
    | ToolEndEvent
    | PermissionRequestEvent
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


class PromptParams(BaseModel):
    """Parameters for the prompt method."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    message: str = Field(..., description="The message to send to the agent")
    context: dict[str, Any] | None = Field(None, description="Optional context including files and selection")
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
    cwd: str | None = Field(None, description="Working directory for the CLI (defaults to current directory)")
    cli_path: str | None = Field(None, description="Path to CLI binary (auto-detected if not provided)")
    debug: bool | None = Field(None, description="Enable debug logging")
    timeout: int | None = Field(None, description="Timeout for requests in milliseconds (default: 300000)", gt=0)
    startup_check: bool = Field(True, description="Probe the CLI with getState after subprocess startup")

    # Provider Configuration
    model: str | None = Field(None, description="Model to use (provider is auto-detected from model ID)")
    fallback_model: str | None = Field(None, description="Fallback model if primary fails")
    max_turns: int | None = Field(None, description="Maximum number of turns", gt=0)
    max_budget_usd: float | None = Field(None, description="Maximum budget in USD", ge=0)
    temperature: float | None = Field(None, description="Sampling temperature (0.0 to 2.0)", ge=0.0, le=2.0)

    # Provider-specific settings
    provider: ProviderName | None = Field(None, description="Provider name (if not provided, auto-detected from model ID)")
    api_key: str | None = Field(None, description="API key for the provider")
    base_url: str | None = Field(None, description="Base URL for the provider API")

    # OpenAI-specific options
    openai_auth_mode: Literal["api-key", "chatgpt"] | None = Field(None, description="OpenAI authentication mode")
    reasoning_effort: Literal["low", "medium", "high"] | None = Field(None, description="OpenAI reasoning effort level (for o1 models)")
    chatgpt_access_token: str | None = Field(None, description="OpenAI ChatGPT access token")
    chatgpt_account_id: str | None = Field(None, description="OpenAI ChatGPT account ID")

    # Azure-specific options
    azure_auth_method: Literal["api-key", "entra-id", "managed-identity"] | None = Field(None, description="Azure authentication method")
    azure_tenant_id: str | None = Field(None, description="Azure tenant ID (for entra-id auth)")
    azure_client_id: str | None = Field(None, description="Azure client ID (for entra-id auth)")
    azure_client_secret: str | None = Field(None, description="Azure client secret (for entra-id auth)")
    azure_resource_name: str | None = Field(None, description="Azure resource name")
    azure_deployment_name: str | None = Field(None, description="Azure deployment name")

    # Execution settings
    auto_mode: bool | None = Field(None, description="Enable auto-mode for autonomous execution")
    unrestricted: bool | None = Field(None, description="Run in unrestricted mode")
    max_iterations: int | None = Field(None, description="Maximum number of iterations in auto-mode", gt=0)
    max_runtime: int | None = Field(None, description="Maximum runtime in minutes", gt=0)
    max_cost: float | None = Field(None, description="Maximum API cost in dollars", ge=0)

    # System prompt settings
    sys_prompt: str | None = Field(None, description="System prompt (inline string or file path)")
    append_sys_prompt: str | None = Field(None, description="Append to system prompt")

    # YOLO (auto-approve) settings
    yolo: str | None = Field(None, description="Auto-approve tool calls matching pattern")
    yolo_timeout: int | None = Field(None, description="Timeout in seconds for auto-approve mode", gt=0)

    # Additional directories
    additional_directories: list[str] | None = Field(None, description="Additional directories to add to workspace")
    add_dir: list[str] | None = Field(None, description="Additional directories (alias)")

    # Extra CLI arguments
    extra_args: list[str] | None = Field(None, description="Additional CLI arguments")

    # Environment variables
    env_vars: AutohandEnvVars | None = Field(None, description="Environment variables to forward to CLI subprocess")

    # Skills configuration
    skills: SkillSettings | None = Field(None, description="Skill settings")
    skill_refs: list[SkillReference] | None = Field(None, description="Direct skill references (convenience)")
    auto_skill: bool | None = Field(None, description="Enable auto-skill for automatic skill selection (legacy)")
    copy_skill_files: bool = Field(True, description="Copy local skill files into ~/.autohand/skills before startup")

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
    continue_: bool | None = Field(None, alias="continue", description="Continue from last session (legacy)")

    # AGENTS.md configuration
    agents_md: AgentsMdSettings | None = Field(None, description="AGENTS.md settings")
    agents_md_enable: bool | None = Field(None, description="Enable AGENTS.md usage (legacy)")
    agents_md_create: bool | None = Field(None, description="Create AGENTS.md if it doesn't exist (legacy)")

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
