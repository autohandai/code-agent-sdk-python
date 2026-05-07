"""Tests for SDK types."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from autohand_sdk.types import (
    AgentsMdSettings,
    ProviderConfigError,
    ProviderName,
    SDKConfig,
    SkillReference,
    Tool,
    create_default_agents_md,
    detect_provider_from_model,
    get_skill_name,
    get_skill_path,
    is_skill_file_path,
    load_agents_md,
    parse_sdk_event,
    validate_provider_config,
)


class TestProviderDetection:
    """Tests for provider detection."""

    def test_detect_openrouter(self) -> None:
        assert detect_provider_from_model("openrouter/quasar-alpha") == ProviderName.OPENROUTER
        assert detect_provider_from_model("or/gpt-4") == ProviderName.OPENROUTER

    def test_detect_anthropic(self) -> None:
        assert detect_provider_from_model("claude-5-sonnet") == ProviderName.ANTHROPIC
        assert detect_provider_from_model("anthropic/claude-3-opus") == ProviderName.ANTHROPIC

    def test_detect_openai(self) -> None:
        assert detect_provider_from_model("gpt-4") == ProviderName.OPENAI
        assert detect_provider_from_model("o1-preview") == ProviderName.OPENAI

    def test_detect_azure(self) -> None:
        assert detect_provider_from_model("azure/gpt-4") == ProviderName.AZURE

    def test_detect_ollama(self) -> None:
        assert detect_provider_from_model("ollama/llama3") == ProviderName.OLLAMA
        assert detect_provider_from_model("llama3:latest") == ProviderName.OLLAMA

    def test_detect_xai(self) -> None:
        assert detect_provider_from_model("grok-beta") == ProviderName.XAI

    def test_detect_cerebras(self) -> None:
        assert detect_provider_from_model("cerebras/llama3") == ProviderName.CEREBRAS

    def test_detect_deepseek(self) -> None:
        assert detect_provider_from_model("deepseek-chat") == ProviderName.DEEPSEEK

    def test_detect_unknown(self) -> None:
        assert detect_provider_from_model("unknown-model") is None


class TestProviderValidation:
    """Tests for provider validation."""

    def test_validate_azure_requires_resource_name(self) -> None:
        config = SDKConfig(azure_deployment_name="test")
        with pytest.raises(ProviderConfigError) as exc_info:
            validate_provider_config(ProviderName.AZURE, config)
        assert "azure_resource_name" in str(exc_info.value)

    def test_validate_azure_requires_deployment_name(self) -> None:
        config = SDKConfig(azure_resource_name="test")
        with pytest.raises(ProviderConfigError) as exc_info:
            validate_provider_config(ProviderName.AZURE, config)
        assert "azure_deployment_name" in str(exc_info.value)

    def test_validate_azure_success(self) -> None:
        config = SDKConfig(azure_resource_name="test", azure_deployment_name="test")
        validate_provider_config(ProviderName.AZURE, config)  # Should not raise

    def test_validate_openai_requires_api_key(self) -> None:
        config = SDKConfig(openai_auth_mode="api-key")
        with pytest.raises(ProviderConfigError) as exc_info:
            validate_provider_config(ProviderName.OPENAI, config)
        assert "api_key" in str(exc_info.value)


class TestSkillReference:
    """Tests for skill references."""

    def test_is_skill_file_path_with_file(self) -> None:
        assert is_skill_file_path("./skills/SKILL.md") is True
        assert is_skill_file_path("/absolute/path/SKILL.md") is True
        assert is_skill_file_path("skill.md") is True

    def test_is_skill_file_path_with_name(self) -> None:
        assert is_skill_file_path("typescript") is False
        assert is_skill_file_path("react") is False

    def test_get_skill_name_from_path(self) -> None:
        assert get_skill_name("./skills/my-skill/SKILL.md") == "my-skill"
        assert get_skill_name("/path/to/SKILL.md") == "to"
        assert get_skill_name("custom.md") == "custom"

    def test_get_skill_name_from_name(self) -> None:
        assert get_skill_name("typescript") == "typescript"

    def test_get_skill_name_from_object(self) -> None:
        ref: SkillReference = {"name": "custom-skill", "path": "./skills/SKILL.md"}
        assert get_skill_name(ref) == "custom-skill"

    def test_get_skill_path_from_path(self) -> None:
        assert get_skill_path("./skills/SKILL.md") == "./skills/SKILL.md"

    def test_get_skill_path_from_name(self) -> None:
        assert get_skill_path("typescript") is None

    def test_get_skill_path_from_object(self) -> None:
        ref: SkillReference = {"name": "custom", "path": "./skills/SKILL.md"}
        assert get_skill_path(ref) == "./skills/SKILL.md"


class TestSDKConfig:
    """Tests for SDKConfig."""

    def test_default_config(self) -> None:
        config = SDKConfig()
        assert config.cwd is None
        assert config.model is None

    def test_config_with_model(self) -> None:
        config = SDKConfig(model="fantail2")
        assert config.model == "fantail2"

    def test_config_auto_detects_provider(self) -> None:
        config = SDKConfig(model="openrouter/quasar-alpha")
        assert config.provider == ProviderName.OPENROUTER

    def test_config_validates_temperature(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            SDKConfig(temperature=3.0)
        assert "temperature" in str(exc_info.value)

    def test_config_validates_negative_temperature(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            SDKConfig(temperature=-0.5)
        assert "temperature" in str(exc_info.value)

    def test_config_valid_temperature(self) -> None:
        config = SDKConfig(temperature=1.5)
        assert config.temperature == 1.5

    def test_config_expands_cwd(self) -> None:
        config = SDKConfig(cwd="~/projects")
        assert config.cwd is not None
        assert "projects" in config.cwd

    def test_config_with_skills(self) -> None:
        config = SDKConfig(skill_refs=["typescript", "./skills/custom/SKILL.md"])
        assert len(config.skill_refs) == 2
        assert config.skill_refs[0] == "typescript"

    def test_config_validates_positive_timeout(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            SDKConfig(timeout=0)
        assert "timeout" in str(exc_info.value)

    def test_config_validates_context_thresholds(self) -> None:
        from autohand_sdk.types import ContextSettings

        with pytest.raises(ValidationError) as exc_info:
            SDKConfig(context=ContextSettings(compression_threshold=1.5))
        assert "compression_threshold" in str(exc_info.value)


class TestSDKEvents:
    """Tests for event parsing helpers."""

    def test_parse_known_event(self) -> None:
        event = parse_sdk_event(
            {"type": "message_update", "messageId": "m1", "delta": "hello"}
        )
        assert not isinstance(event, dict)
        assert event.type == "message_update"
        assert event.message_id == "m1"

    def test_parse_unknown_event_returns_raw_dict(self) -> None:
        raw = {"type": "future_event", "value": 1}
        assert parse_sdk_event(raw) is raw


class TestToolEnum:
    """Tests for Tool enum."""

    def test_tool_values(self) -> None:
        assert Tool.READ == "read"
        assert Tool.WRITE == "write"
        assert Tool.EDIT == "edit"
        assert Tool.BASH == "bash"
        assert Tool.BROWSE == "browse"
        assert Tool.GREP_SEARCH == "grep_search"
        assert Tool.LIST_DIR == "list_dir"


class TestAgentsMdSettings:
    """Tests for AGENTS.md settings."""

    def test_default_settings(self) -> None:
        settings = AgentsMdSettings()
        assert settings.enable is None
        assert settings.create is None

    def test_load_agents_md(self, tmp_path) -> None:
        md_path = tmp_path / "AGENTS.md"
        md_path.write_text("# AGENTS.md\n\n## Tools\n\n- read")
        settings = load_agents_md(str(md_path))
        assert settings.path == str(md_path)

    def test_create_default_agents_md(self, tmp_path) -> None:
        md_path = tmp_path / "AGENTS.md"
        create_default_agents_md(str(md_path))
        assert md_path.exists()
        content = md_path.read_text()
        assert "AGENTS.md" in content
        assert "read" in content
